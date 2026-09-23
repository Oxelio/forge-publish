import json
import subprocess
from pathlib import Path

import pytest

from forge_publish.config import TOKEN_ENV_VAR, Config
from forge_publish.errors import PackageError
from forge_publish.publishers import npm


class FakeClient:
    def __init__(self, *, token: str | None = "secret-token") -> None:
        self.config = Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
            token=token,
        )


def _write_package(directory: Path, data: object) -> None:
    directory.mkdir()
    (directory / "package.json").write_text(
        json.dumps(data),
        encoding="utf-8",
    )


def test_npm_packs_without_credentials_before_authenticated_publish(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "package"
    _write_package(
        package_dir,
        {
            "name": "example",
            "version": "1.0.0",
        },
    )
    (package_dir / ".npmrc").write_text(
        (
            "strict-ssl=false\n"
            "//forge.example.com/api/packages/Software/npm/:_authToken=project-token\n"
        ),
        encoding="utf-8",
    )

    observed_npmrc: Path | None = None
    observed_archive: Path | None = None
    commands: list[list[str]] = []

    monkeypatch.setenv(
        TOKEN_ENV_VAR,
        "environment-secret-token",
    )
    monkeypatch.setenv("NPM_CONFIG_STRICT_SSL", "false")
    monkeypatch.setattr(
        npm.shutil,
        "which",
        lambda _: "npm",
    )

    def fake_run(command, cwd, check, env):
        nonlocal observed_npmrc, observed_archive

        commands.append(command)
        assert check is True
        assert TOKEN_ENV_VAR not in env

        if command[1] == "pack":
            assert cwd == package_dir
            assert not any(item.startswith("--userconfig=") for item in command)
            destination = Path(command[2].split("=", 1)[1])
            assert not (destination / ".npmrc").exists()
            observed_archive = destination / "example-1.0.0.tgz"
            observed_archive.write_bytes(b"package")
            return

        assert command[1] == "publish"
        assert observed_archive is not None
        assert cwd == observed_archive.parent
        assert cwd != package_dir
        assert command[2] == str(observed_archive)
        assert "--strict-ssl=true" in command
        assert "--ignore-scripts" in command

        userconfig = next(
            item.split("=", 1)[1]
            for item in command
            if item.startswith("--userconfig=")
        )
        observed_npmrc = Path(userconfig)
        content = observed_npmrc.read_text(encoding="utf-8")

        assert "secret-token" in content
        assert "project-token" not in content
        assert "strict-ssl=true" in content
        assert ("//forge.example.com/api/packages/Software/npm/:_authToken=") in content

    monkeypatch.setattr(
        npm.subprocess,
        "run",
        fake_run,
    )

    npm.publish(
        client=FakeClient(),
        directory=package_dir,
        dry_run=False,
    )

    assert [command[1] for command in commands] == ["pack", "publish"]
    assert observed_npmrc is not None
    assert not observed_npmrc.exists()
    assert observed_archive is not None
    assert not observed_archive.exists()


def test_npm_dry_run_does_not_require_token_or_npm(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "package"
    _write_package(
        package_dir,
        {
            "name": "example",
            "version": "1.0.0",
        },
    )

    def fail(_):
        raise AssertionError("npm should not be resolved during dry-run")

    monkeypatch.setattr(npm.shutil, "which", fail)

    npm.publish(
        client=FakeClient(token=None),
        directory=package_dir,
        dry_run=True,
    )


def test_npm_requires_token(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})

    with pytest.raises(PackageError, match="No Forgejo token"):
        npm.publish(
            client=FakeClient(token=None),
            directory=package_dir,
            dry_run=False,
        )


def test_npm_requires_executable(tmp_path: Path, monkeypatch) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})
    monkeypatch.setattr(npm.shutil, "which", lambda _: None)

    with pytest.raises(PackageError, match="npm is not installed"):
        npm.publish(
            client=FakeClient(),
            directory=package_dir,
            dry_run=False,
        )


def test_npm_reports_pack_failure(tmp_path: Path, monkeypatch) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})
    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")

    def fail_pack(command, cwd, check, env):
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(npm.subprocess, "run", fail_pack)

    with pytest.raises(PackageError, match="npm pack failed with exit code 2"):
        npm.publish(
            client=FakeClient(),
            directory=package_dir,
            dry_run=False,
        )


def test_npm_reports_pack_execution_failure(tmp_path: Path, monkeypatch) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})
    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")

    def fail_pack(command, cwd, check, env):
        raise OSError("permission denied")

    monkeypatch.setattr(npm.subprocess, "run", fail_pack)

    with pytest.raises(
        PackageError, match="Unable to execute npm pack: permission denied"
    ):
        npm.publish(
            client=FakeClient(),
            directory=package_dir,
            dry_run=False,
        )


def test_npm_reports_publish_failure(tmp_path: Path, monkeypatch) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})
    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")

    def fail_publish(command, cwd, check, env):
        if command[1] == "pack":
            destination = Path(command[2].split("=", 1)[1])
            (destination / "example-1.0.0.tgz").write_bytes(b"package")
            return
        raise subprocess.CalledProcessError(3, command)

    monkeypatch.setattr(npm.subprocess, "run", fail_publish)

    with pytest.raises(PackageError, match="npm publish failed with exit code 3"):
        npm.publish(
            client=FakeClient(),
            directory=package_dir,
            dry_run=False,
        )


def test_npm_reports_publish_execution_failure(tmp_path: Path, monkeypatch) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})
    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")

    def fail_publish(command, cwd, check, env):
        if command[1] == "pack":
            destination = Path(command[2].split("=", 1)[1])
            (destination / "example-1.0.0.tgz").write_bytes(b"package")
            return
        raise OSError("executable disappeared")

    monkeypatch.setattr(npm.subprocess, "run", fail_publish)

    with pytest.raises(
        PackageError,
        match="Unable to execute npm publish: executable disappeared",
    ):
        npm.publish(
            client=FakeClient(),
            directory=package_dir,
            dry_run=False,
        )


def test_npm_reports_temporary_file_failure(tmp_path: Path, monkeypatch) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})
    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")

    def fake_run(command, cwd, check, env):
        destination = Path(command[2].split("=", 1)[1])
        (destination / "example-1.0.0.tgz").write_bytes(b"package")

    monkeypatch.setattr(npm.subprocess, "run", fake_run)

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(npm.Path, "write_text", fail_write)

    with pytest.raises(
        PackageError, match="Unable to create or use temporary npm files"
    ):
        npm.publish(
            client=FakeClient(),
            directory=package_dir,
            dry_run=False,
        )


@pytest.mark.parametrize(
    "package",
    [
        {},
        {"name": "", "version": "1.0.0"},
        {"name": "example", "version": ""},
        {"name": 42, "version": "1.0.0"},
        {"name": "example", "version": 42},
    ],
)
def test_npm_rejects_invalid_metadata(
    tmp_path: Path,
    package: object,
) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, package)

    with pytest.raises(PackageError):
        npm.publish(
            client=FakeClient(),
            directory=package_dir,
            dry_run=True,
        )
