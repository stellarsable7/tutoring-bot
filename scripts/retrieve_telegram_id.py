import getpass
import json
import urllib.error
import urllib.request


def main() -> int:
    token = getpass.getpass("Paste the BotFather token (hidden): ").strip()
    if not token:
        print("No token entered.")
        return 1
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/getUpdates",
        headers={"User-Agent": "amath-bot-local-setup/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        print(f"Could not contact Telegram: {error}")
        return 1
    if not payload.get("ok"):
        print("Telegram rejected the token. Retrieve a fresh token from BotFather and try again.")
        return 1

    people: dict[int, str] = {}
    for update in payload.get("result", []):
        message = update.get("message") or update.get("edited_message") or {}
        sender = message.get("from") or {}
        if isinstance(sender.get("id"), int) and not sender.get("is_bot", False):
            name = " ".join(
                part for part in (sender.get("first_name"), sender.get("last_name")) if part
            )
            people[sender["id"]] = name or sender.get("username") or "Telegram user"
    if not people:
        print("No user message found. Send your bot 'hello', wait a moment, and run this again.")
        return 1
    print("\nTelegram users found:")
    for user_id, name in people.items():
        print(f"  {name}: {user_id}")
    print("\nYour AMATH_TUTOR_TELEGRAM_ID is the number beside your name.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
