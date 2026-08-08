import argparse
import getpass
import json
import os
import secrets
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


def _write_env_atomic(output: Path, contents: str, *, force: bool) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w") as output_file:
            os.fchmod(output_file.fileno(), 0o600)
            output_file.write(contents)
            output_file.flush()
            os.fsync(output_file.fileno())

        if force:
            os.replace(temporary, output)
        else:
            os.link(temporary, output)
            temporary.unlink()

        directory_descriptor = os.open(
            output.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--telegram-id", required=True, type=int)
    parser.add_argument("--output", type=Path, default=Path(".env"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if os.path.lexists(args.output) and not args.force:
        print(f"{args.output} already exists; use --force only to replace it deliberately.")
        return 1

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

    openrouter_api_key = getpass.getpass(
        "Paste AMATH_OPENROUTER_API_KEY (hidden): "
    ).strip()
    if not openrouter_api_key:
        print("AMATH_OPENROUTER_API_KEY must not be blank.")
        return 1

    contents = "\n".join(
        (
            f"POSTGRES_PASSWORD={secrets.token_urlsafe(32)}",
            f"AMATH_TELEGRAM_BOT_TOKEN={token}",
            f"AMATH_TUTOR_TELEGRAM_ID={args.telegram_id}",
            f"AMATH_REVIEW_CALLBACK_SECRET={secrets.token_urlsafe(48)}",
            f"AMATH_OPENROUTER_API_KEY={openrouter_api_key}",
            "",
        )
    )
    try:
        _write_env_atomic(args.output, contents, force=args.force)
    except FileExistsError:
        print(f"{args.output} already exists; use --force only to replace it deliberately.")
        return 1
    print(f"Configuration saved securely for @{payload['result']['username']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
