import argparse
import getpass
import json
import secrets
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telegram-id", required=True, type=int)
    parser.add_argument("--output", type=Path, default=Path(".env"))
    args = parser.parse_args()

    token = getpass.getpass("Paste the NEW BotFather token (hidden): ").strip()
    if not token or ":" not in token:
        print("That does not look like a Telegram bot token.")
        return 1
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/getMe",
        headers={"User-Agent": "amath-bot-local-setup/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        print(f"Telegram did not accept the token: {error}")
        return 1
    if not payload.get("ok") or not payload.get("result", {}).get("username"):
        print("Telegram did not accept the token.")
        return 1

    contents = "\n".join(
        (
            f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}",
            f"AMATH_TELEGRAM_BOT_TOKEN={token}",
            f"AMATH_TUTOR_TELEGRAM_ID={args.telegram_id}",
            f"AMATH_REVIEW_CALLBACK_SECRET={secrets.token_urlsafe(48)}",
            "",
        )
    )
    args.output.write_text(contents)
    args.output.chmod(0o600)
    print(f"Configuration saved securely for @{payload['result']['username']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
