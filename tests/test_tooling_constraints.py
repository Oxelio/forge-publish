import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "tooling_constraints", ROOT / ".github/scripts/tooling-constraints.py"
)
tooling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tooling)


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "requirements").mkdir()
    (tmp_path / "requirements/generator.txt").write_text("uv==1.2.3\n")
    (tmp_path / "requirements/tooling.txt").write_text(
        tooling.HEADER + "ruff==1.0.0\ncommitizen==2.0.0\n"
    )
    (tmp_path / ".pre-commit-config.yaml").write_text(
        "repos:\n"
        "  - repo: https://github.com/astral-sh/ruff-pre-commit\n"
        "    rev: v1.0.0\n"
        "    hooks: [{id: ruff-check}]\n"
        "  - repo: https://github.com/commitizen-tools/commitizen\n"
        "    rev: v2.0.0\n"
        "    hooks: [{id: commitizen}]\n"
    )
    monkeypatch.setattr(tooling, "version", lambda _: "1.2.3")
    return tmp_path


def compiler(monkeypatch: pytest.MonkeyPatch, content: str) -> None:
    def run(command, **kwargs):
        output = Path(command[command.index("--output-file") + 1])
        output.write_text(content, encoding="utf-8")

    monkeypatch.setattr(tooling.subprocess, "run", run)


@pytest.mark.parametrize("drift", ["constraints", "hooks", "none"])
def test_check_detects_drift_without_writing(
    repository: Path, monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    compiler(monkeypatch, "ruff==1.0.0\ncommitizen==2.0.0\n")
    if drift == "constraints":
        (repository / "requirements/tooling.txt").write_text("ruff==0.9.0\n")
    elif drift == "hooks":
        hooks = repository / ".pre-commit-config.yaml"
        hooks.write_text(hooks.read_text().replace("v1.0.0", "v0.9.0"))
    before = {
        path: path.read_bytes() for path in repository.rglob("*") if path.is_file()
    }

    assert tooling.generate(repository, check=True, upgrades=[]) is (drift == "none")
    assert all(path.read_bytes() == content for path, content in before.items())


def test_generation_aligns_hooks_and_preserves_hook_options(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compiler(monkeypatch, "ruff==1.1.0 ; sys_platform == 'win32'\ncommitizen==2.1.0\n")

    assert tooling.generate(repository, check=False, upgrades=["ruff"])

    config = (repository / ".pre-commit-config.yaml").read_text()
    assert "rev: v1.1.0" in config
    assert "rev: v2.1.0" in config
    assert "hooks: [{id: ruff-check}]" in config
    assert "hooks: [{id: commitizen}]" in config


@pytest.mark.parametrize("failure", ["resolver", "ambiguous-hook", "missing-hook"])
def test_failed_generation_preserves_reviewed_files(
    repository: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    if failure == "resolver":

        def fail(*args, **kwargs):
            raise subprocess.CalledProcessError(1, "uv")

        monkeypatch.setattr(tooling.subprocess, "run", fail)
    elif failure == "ambiguous-hook":
        compiler(monkeypatch, "ruff==1.0.0\nruff==2.0.0\ncommitizen==2.0.0\n")
    else:
        compiler(monkeypatch, "ruff==1.0.0\n")
    before = {
        path: path.read_bytes() for path in repository.rglob("*") if path.is_file()
    }

    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        tooling.generate(repository, check=False, upgrades=[])

    assert all(path.read_bytes() == content for path, content in before.items())


def test_wrong_generator_version_is_rejected_before_resolution(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tooling, "version", lambda _: "9.9.9")

    with pytest.raises(ValueError, match="pinned requirements/generator.txt"):
        tooling.generate(repository, check=False, upgrades=[])
