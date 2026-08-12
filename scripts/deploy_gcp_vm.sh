#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "usage: $0 IMAGE_REFERENCE" >&2
  exit 2
fi

readonly IMAGE_REFERENCE="$1"
readonly CONTAINER_NAME="amath-bot"
readonly STATE_DIR="/var/lib/amath-bot"
readonly ENV_FILE="/run/amath-bot.env"
readonly PREVIOUS_IMAGE_FILE="$STATE_DIR/previous-image"
readonly CURRENT_IMAGE_FILE="$STATE_DIR/current-image"

case "$IMAGE_REFERENCE" in
  asia-southeast1-docker.pkg.dev/chloe-tutoring-bot/amath-bot/amath-bot@sha256:*) ;;
  *)
    echo "refusing unexpected image reference" >&2
    exit 2
    ;;
esac

secret() {
  local value
  value="$(gcloud secrets versions access latest --secret="$1" --project=chloe-tutoring-bot)"
  if [[ -z "$value" ]]; then
    echo "required secret $1 is empty" >&2
    return 1
  fi
  printf '%s' "$value"
}

cleanup() {
  if [[ "${BASH_SUBSHELL:-0}" -eq 0 ]]; then
    rm -f "$ENV_FILE"
  fi
}
trap cleanup EXIT

install -d -m 0700 "$STATE_DIR"
umask 077

DB_PASSWORD="$(secret amath-db-password)"
cat >"$ENV_FILE" <<EOF
AMATH_DATABASE_URL=postgresql+asyncpg://amath:${DB_PASSWORD}@127.0.0.1:5432/amath_bot
AMATH_TIMEZONE=Asia/Singapore
AMATH_TELEGRAM_BOT_TOKEN=$(secret amath-telegram-token)
AMATH_TUTOR_TELEGRAM_ID=$(secret amath-tutor-telegram-id)
AMATH_REVIEW_CALLBACK_SECRET=$(secret amath-review-callback-secret)
AMATH_OPENROUTER_API_KEY=$(secret amath-openrouter-key)
AMATH_OPENROUTER_URL=https://openrouter.ai/api/v1
AMATH_GEMINI_API_KEY=$(secret amath-gemini-api-key)
AMATH_DOCUMENT_AI_PROJECT_ID=chloe-tutoring-bot
AMATH_DOCUMENT_AI_LOCATION=us
AMATH_DOCUMENT_AI_PROCESSOR_ID=$(secret amath-document-ai-processor-id)
EOF
unset DB_PASSWORD

gcloud auth configure-docker asia-southeast1-docker.pkg.dev --quiet >/dev/null
docker pull "$IMAGE_REFERENCE"

docker run --rm --network host --env-file "$ENV_FILE" \
  -e AMATH_TELEGRAM_DRY_RUN=true \
  "$IMAGE_REFERENCE"

docker run --rm --network host --env-file "$ENV_FILE" \
  "$IMAGE_REFERENCE" alembic upgrade head

PREVIOUS_IMAGE=""
if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  PREVIOUS_IMAGE="$(docker inspect --format='{{.Config.Image}}' "$CONTAINER_NAME")"
  printf '%s\n' "$PREVIOUS_IMAGE" >"$PREVIOUS_IMAGE_FILE"
  docker stop --time 30 "$CONTAINER_NAME" >/dev/null
  docker rm "$CONTAINER_NAME" >/dev/null
fi

start_bot() {
  docker run -d \
    --name "$CONTAINER_NAME" \
    --network host \
    --restart unless-stopped \
    --env-file "$ENV_FILE" \
    --log-driver=journald \
    "$1" >/dev/null
}

rollback() {
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  if [[ -n "$PREVIOUS_IMAGE" ]]; then
    echo "new container failed; restoring previous image" >&2
    start_bot "$PREVIOUS_IMAGE"
  fi
}

start_bot "$IMAGE_REFERENCE"

healthy=false
for _ in $(seq 1 30); do
  if [[ "$(docker inspect --format='{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null || true)" != true ]]; then
    break
  fi
  if docker logs "$CONTAINER_NAME" 2>&1 | grep -Fq 'starting Telegram polling'; then
    healthy=true
    break
  fi
  sleep 2
done

if [[ "$healthy" != true ]]; then
  docker logs "$CONTAINER_NAME" 2>&1 | tail -100 >&2 || true
  rollback
  exit 1
fi

printf '%s\n' "$IMAGE_REFERENCE" >"$CURRENT_IMAGE_FILE"
echo "deployed $IMAGE_REFERENCE"
