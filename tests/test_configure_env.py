from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "configure_env.py"
_SPEC = importlib.util.spec_from_file_location("configure_env", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
configure_env = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(configure_env)


def _telegram_response() -> io.BytesIO:
    return io.BytesIO(b'{"ok": true, "result": {"username": "amath_test_bot"}}')


def test_main_writes_hidden_openrouter_key_to_private_env(
    monkeypatch, tmp_path, capsys
) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / ".env"
    telegram_token = "123456:telegram-secret"
    openrouter_key = "sk-or-v1-openrouter-secret"
    secrets = iter((telegram_token, openrouter_key))
    monkeypatch.setattr(configure_env.getpass, "getpass", lambda _prompt: next(secrets))
    monkeypatch.setattr(
        configure_env.urllib.request,
        "urlopen",
        lambda _request, timeout: _telegram_response(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_env.py",
            "--output",
            str(output),
            "--telegram-id",
            "123",
        ],
    )

    assert configure_env.main() == 0

    contents = output.read_text()
    captured = capsys.readouterr()
    terminal_output = captured.out + captured.err
    assert f"AMATH_OPENROUTER_API_KEY={openrouter_key}" in contents
    assert output.stat().st_mode & 0o777 == 0o600
    assert telegram_token not in terminal_output
    assert openrouter_key not in terminal_output


def test_main_rejects_blank_openrouter_key_without_writing_secrets(
    monkeypatch, tmp_path, capsys
) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / ".env"
    telegram_token = "123456:telegram-secret"
    secrets = iter((telegram_token, "   "))
    monkeypatch.setattr(configure_env.getpass, "getpass", lambda _prompt: next(secrets))
    monkeypatch.setattr(
        configure_env.urllib.request,
        "urlopen",
        lambda _request, timeout: _telegram_response(),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "configure_env.py",
            "--output",
            str(output),
            "--telegram-id",
            "123",
        ],
    )

    assert configure_env.main() == 1

    captured = capsys.readouterr()
    terminal_output = captured.out + captured.err
    assert "AMATH_OPENROUTER_API_KEY" in captured.out
    assert not output.exists()
    assert telegram_token not in terminal_output
