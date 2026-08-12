import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "deploy_gcp_vm.sh"


def test_deploy_script_requires_exactly_one_image() -> None:
    result = subprocess.run([SCRIPT], check=False, capture_output=True, text=True)

    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_deploy_script_rejects_images_outside_production_registry() -> None:
    result = subprocess.run(
        [SCRIPT, "docker.io/example/amath-bot@sha256:not-trusted"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert result.stderr == "refusing unexpected image reference\n"


def test_cleanup_only_removes_environment_from_top_level_shell() -> None:
    contents = SCRIPT.read_text()

    assert '"${BASH_SUBSHELL:-0}" -eq 0' in contents
