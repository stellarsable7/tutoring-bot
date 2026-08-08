from __future__ import annotations

import importlib.util
import io
import os
import sys
from pathlib import Path

import pytest

_SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "configure_env.py"
_SPEC = importlib.util.spec_from_file_location("configure_env", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
configure_env = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(configure_env)


def _telegram_response() -> io.BytesIO:
    return io.BytesIO(b'{"ok": true, "result": {"username": "amath_test_bot"}}')


def _prepare_successful_run(monkeypatch, output: Path, *, force: bool = False) -> None:  # type: ignore[no-untyped-def]
    secrets = iter(("123456:telegram-secret", "sk-or-v1-openrouter-secret"))
    monkeypatch.setattr(configure_env.getpass, "getpass", lambda _prompt: next(secrets))
    monkeypatch.setattr(
        configure_env.urllib.request,
        "urlopen",
        lambda _request, timeout: _telegram_response(),
    )
    argv = [
        "configure_env.py",
        "--output",
        str(output),
        "--telegram-id",
        "123",
    ]
    if force:
        argv.append("--force")
    monkeypatch.setattr(sys, "argv", argv)


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


def test_main_refuses_existing_output_without_force(
    monkeypatch, tmp_path, capsys
) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / ".env"
    output.write_text("existing\n")
    monkeypatch.setattr(
        configure_env.getpass,
        "getpass",
        lambda _prompt: pytest.fail("must refuse before prompting"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["configure_env.py", "--output", str(output), "--telegram-id", "123"],
    )

    assert configure_env.main() == 1
    assert output.read_text() == "existing\n"
    assert "already exists" in capsys.readouterr().out


def test_main_force_atomically_replaces_existing_output(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / ".env"
    output.write_text("existing\n")
    _prepare_successful_run(monkeypatch, output, force=True)

    assert configure_env.main() == 0
    assert "AMATH_OPENROUTER_API_KEY=sk-or-v1-openrouter-secret" in output.read_text()
    assert output.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("dangling", [False, True])
def test_main_refuses_symlink_without_force(
    monkeypatch, tmp_path, dangling, capsys
) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "target"
    if not dangling:
        target.write_text("target contents\n")
    output = tmp_path / ".env"
    output.symlink_to(target)
    monkeypatch.setattr(
        configure_env.getpass,
        "getpass",
        lambda _prompt: pytest.fail("must refuse before prompting"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["configure_env.py", "--output", str(output), "--telegram-id", "123"],
    )

    assert configure_env.main() == 1
    assert output.is_symlink()
    assert not target.exists() if dangling else target.read_text() == "target contents\n"
    assert "already exists" in capsys.readouterr().out


@pytest.mark.parametrize("dangling", [False, True])
def test_main_force_replaces_symlink_without_touching_target(
    monkeypatch, tmp_path, dangling
) -> None:  # type: ignore[no-untyped-def]
    target = tmp_path / "target"
    if not dangling:
        target.write_text("target contents\n")
    output = tmp_path / ".env"
    output.symlink_to(target)
    _prepare_successful_run(monkeypatch, output, force=True)

    assert configure_env.main() == 0
    assert not output.is_symlink()
    assert output.stat().st_mode & 0o777 == 0o600
    assert not target.exists() if dangling else target.read_text() == "target contents\n"


def test_main_removes_temporary_file_when_atomic_replace_fails(
    monkeypatch, tmp_path
) -> None:  # type: ignore[no-untyped-def]
    output = tmp_path / ".env"
    _prepare_successful_run(monkeypatch, output, force=True)
    before = set(tmp_path.iterdir())
    monkeypatch.setattr(
        os,
        "replace",
        lambda _source, _destination: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        configure_env.main()

    assert set(tmp_path.iterdir()) == before
