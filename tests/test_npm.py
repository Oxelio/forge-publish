import json
import os
import shutil
import subprocess
import tarfile
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


def _mock_supported_npm(monkeypatch) -> None:
    monkeypatch.setattr(
        npm,
        "_get_npm_version",
        lambda *_args, **_kwargs: "11.19.0",
    )


@pytest.mark.parametrize("allow_pack_scripts", [False, True])
def test_npm_real_pack_lifecycle_policy(
    tmp_path: Path, monkeypatch, allow_pack_scripts: bool
) -> None:
    npm_executable = shutil.which("npm")
    if npm_executable is None:
        pytest.skip("npm is required for the lifecycle fixture")
    npm_version = npm._get_npm_version(
        npm_executable, environment=npm._sanitize_npm_environment(os.environ)
    )
    try:
        npm._require_supported_npm(npm_version)
    except PackageError as exc:
        if npm.NPM_VERSION_PATTERN.fullmatch(npm_version) is None:
            raise
        pytest.skip(f"Supported npm is required for the lifecycle fixture: {exc}")
    package_dir = tmp_path / "package"
    shutil.copytree(Path(__file__).parent / "fixtures" / "npm_lifecycle", package_dir)
    (package_dir / ".npmrc").write_text(
        f"ignore-scripts={str(allow_pack_scripts).lower()}\n"
        f"cache={tmp_path.as_posix()}/cache\nupdate-notifier=false\n",
        encoding="utf-8",
    )
    monkeypatch.setenv(TOKEN_ENV_VAR, "fake-forge-token")
    monkeypatch.setenv("NPM_TOKEN", "fake-npm-token")
    monkeypatch.setenv("NODE_AUTH_TOKEN", "fake-node-token")
    monkeypatch.setenv(npm.NPM_PUBLISH_TOKEN_ENV_VAR, "fake-publish-token")
    monkeypatch.setenv("FoRgE_PuBlIsH_NpM_AuTh_ToKeN", "fake-mixed-case-token")
    monkeypatch.setenv("NpM_CoNfIg_Ignore_Scripts", "false")
    run_npm = npm._run_npm
    published = []

    def run_without_upload(command, *, cwd, environment, operation):
        if operation == "pack":
            run_npm(command, cwd=cwd, environment=environment, operation=operation)
        else:
            assert operation == "publish"
            assert "--ignore-scripts" in command
            assert Path(command[2]).is_file()
            with tarfile.open(command[2]) as archive:
                marker = "package/lifecycle-events.txt"
                if allow_pack_scripts:
                    with archive.extractfile(marker) as file:
                        assert file.read() == b"prepack\nprepare\n"
                else:
                    assert marker not in archive.getnames()
            published.append(command)

    monkeypatch.setattr(npm, "_run_npm", run_without_upload)
    options = {"allow_pack_scripts": True} if allow_pack_scripts else {}
    npm.publish(client=FakeClient(), directory=package_dir, dry_run=False, **options)
    assert len(published) == 1
    marker = package_dir / "lifecycle-events.txt"
    if allow_pack_scripts:
        assert marker.read_text(encoding="utf-8") == "prepack\nprepare\npostpack\n"
    else:
        assert not marker.exists()


@pytest.mark.parametrize("allow_pack_scripts", [False, True])
@pytest.mark.parametrize("failure_operation", [None, "--version", "pack", "publish"])
def test_npm_packs_without_credentials_before_authenticated_publish(
    tmp_path: Path,
    monkeypatch,
    allow_pack_scripts: bool,
    failure_operation: str | None,
    capsys,
) -> None:
    package_dir = tmp_path / "package"
    _write_package(
        package_dir,
        {
            "name": "example",
            "version": "1.0.0",
            "publishConfig": {
                "registry": "https://registry.invalid/",
                "strict-ssl": False,
            },
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
    observed_temporary_directory: Path | None = None
    commands: list[list[str]] = []
    preparation_environment: dict[str, str] | None = None

    monkeypatch.setenv(TOKEN_ENV_VAR, "environment-secret-token")
    monkeypatch.setenv("NPM_TOKEN", "npm-token")
    monkeypatch.setenv("NODE_AUTH_TOKEN", "node-token")
    monkeypatch.setenv("NPM_CONFIG_STRICT_SSL", "false")
    monkeypatch.setenv("npm_config_registry", "https://environment.invalid/")
    monkeypatch.setenv("NODE_EXTRA_CA_CERTS", "/tmp/forge-ca.pem")
    monkeypatch.setenv(npm.NPM_PUBLISH_TOKEN_ENV_VAR, "inherited-publish-token")
    monkeypatch.setenv("FoRgE_PuBlIsH_NpM_AuTh_ToKeN", "mixed-case-publish-token")
    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")
    original_environment = dict(os.environ)
    client = FakeClient()
    token = client.config.token
    assert token is not None
    forbidden_values = [
        token,
        "environment-secret-token",
        "inherited-publish-token",
        "mixed-case-publish-token",
    ]

    def fake_run(command, check, env, cwd=None, **kwargs):
        nonlocal observed_npmrc, observed_archive, preparation_environment
        nonlocal observed_temporary_directory

        commands.append(command)
        assert check is True
        assert TOKEN_ENV_VAR not in env
        assert "NPM_TOKEN" not in env
        assert "NODE_AUTH_TOKEN" not in env
        assert not any(key.casefold().startswith("npm_config_") for key in env)
        assert env["NODE_EXTRA_CA_CERTS"] == "/tmp/forge-ca.pem"
        assert all(value not in " ".join(command) for value in forbidden_values)
        assert dict(os.environ) == original_environment

        if command[1] in {"--version", "pack"}:
            assert not any(
                key.casefold() == npm.NPM_PUBLISH_TOKEN_ENV_VAR.casefold()
                for key in env
            )
            assert all(value not in env.values() for value in forbidden_values)
            if preparation_environment is None:
                preparation_environment = env
            else:
                assert env is preparation_environment

        if command[1] == "--version":
            assert command == ["npm", "--version"]
            assert kwargs == {"capture_output": True, "text": True}
            if failure_operation == "--version":
                raise subprocess.CalledProcessError(2, command, output=token)
            return subprocess.CompletedProcess(command, 0, stdout="11.0.0\n")

        if command[1] == "pack":
            assert cwd == package_dir
            expected_option = (
                "--ignore-scripts=false" if allow_pack_scripts else "--ignore-scripts"
            )
            assert command == ["npm", "pack", command[2], expected_option]
            assert not any(item.startswith("--userconfig=") for item in command)
            destination = Path(command[2].split("=", 1)[1])
            observed_temporary_directory = destination
            assert not (destination / ".npmrc").exists()
            if failure_operation == "pack":
                raise subprocess.CalledProcessError(2, command, stderr=token)
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
        assert (
            "--registry=https://forge.example.com/api/packages/Software/npm/" in command
        )

        userconfig = next(
            item.split("=", 1)[1]
            for item in command
            if item.startswith("--userconfig=")
        )
        observed_npmrc = Path(userconfig)
        content = observed_npmrc.read_text(encoding="utf-8")

        assert content == (
            "registry=https://forge.example.com/api/packages/Software/npm/\n"
            "strict-ssl=true\n"
            "//forge.example.com/api/packages/Software/npm/:_authToken="
            "${FORGE_PUBLISH_NPM_AUTH_TOKEN}\n"
        )
        assert all(value not in content for value in forbidden_values)
        for file in cwd.iterdir():
            assert all(
                value.encode() not in file.read_bytes() for value in forbidden_values
            )
        assert env is not preparation_environment
        assert preparation_environment is not None
        assert env == {**preparation_environment, npm.NPM_PUBLISH_TOKEN_ENV_VAR: token}
        assert not any(
            key.casefold() == npm.NPM_PUBLISH_TOKEN_ENV_VAR.casefold()
            for key in preparation_environment
        )
        assert "project-token" not in content
        assert "strict-ssl=true" in content
        assert ("//forge.example.com/api/packages/Software/npm/:_authToken=") in content
        if failure_operation == "publish":
            raise subprocess.CalledProcessError(3, command, output=token, stderr=token)

    monkeypatch.setattr(npm.subprocess, "run", fake_run)

    def publish():
        npm.publish(
            client=client,
            directory=package_dir,
            dry_run=False,
            allow_pack_scripts=allow_pack_scripts,
        )

    operations = ["--version", "pack", "publish"]
    if failure_operation is None:
        publish()
    else:
        with pytest.raises(PackageError, match="failed with exit code") as error:
            publish()
        assert all(value not in str(error.value) for value in forbidden_values)
        operations = operations[: operations.index(failure_operation) + 1]
    assert [command[1] for command in commands] == operations
    if observed_npmrc is not None:
        assert not observed_npmrc.exists()
    if observed_archive is not None:
        assert not observed_archive.exists()
    if observed_temporary_directory is not None:
        assert not observed_temporary_directory.exists()
    assert dict(os.environ) == original_environment
    output = capsys.readouterr()
    assert all(value not in output.out + output.err for value in forbidden_values)
    assert ("published successfully" in output.out) is (failure_operation is None)


def test_sanitize_npm_environment_removes_tokens_and_all_npm_config() -> None:
    source = {
        "FoRgE_PuBlIsH_ToKeN": "forge-token",
        "nPm_ToKeN": "npm-token",
        "NoDe_AuTh_ToKeN": "node-token",
        npm.NPM_PUBLISH_TOKEN_ENV_VAR: "publish-token",
        "FoRgE_PuBlIsH_NpM_AuTh_ToKeN": "mixed-case-token",
        "NPM_CONFIG_STRICT_SSL": "false",
        "npm_config_registry": "https://environment.invalid/",
        "NpM_CoNfIg_UsErCoNfIg": "/tmp/untrusted-npmrc",
        "npm_config_//forge.example.com/api/packages/Software/npm/:_authToken": (
            "environment-token"
        ),
        "PATH": "/usr/bin",
    }
    original = source.copy()

    sanitized = npm._sanitize_npm_environment(source)

    assert sanitized == {"PATH": "/usr/bin"}
    assert source == original


def test_sanitize_npm_environment_preserves_network_and_trust_variables() -> None:
    source = {
        "HTTP_PROXY": "http://proxy.example.com",
        "HTTPS_PROXY": "https://proxy.example.com",
        "NO_PROXY": "localhost,127.0.0.1",
        "NODE_EXTRA_CA_CERTS": "/tmp/ca.pem",
        "PATH": "/usr/bin",
    }

    sanitized = npm._sanitize_npm_environment(source)

    assert sanitized == source


@pytest.mark.parametrize(
    "version",
    [
        "11.0.0",
        "11.0.0+build.1",
        "11.0.1",
        "11.0.1-beta.1",
        "12.1.0",
    ],
)
def test_accepts_supported_npm_versions(version: str) -> None:
    npm._require_supported_npm(version)


@pytest.mark.parametrize(
    "version",
    [
        "9.9.9",
        "10.4.9",
        "10.5.1",
        "10.5.2",
        "10.9.9",
        "11.0.0-alpha.1",
        "11.0.0-beta.1",
        "11.0.0-rc.0",
        "11.0.0-rc.0+build.1",
    ],
)
def test_rejects_unsupported_npm_versions(version: str) -> None:
    with pytest.raises(PackageError, match="npm 11.0.0 or newer is required"):
        npm._require_supported_npm(version)


@pytest.mark.parametrize(
    "version",
    [
        "",
        "npm 11.19.0",
        "11",
        "11.19",
        "unknown",
    ],
)
def test_rejects_unparseable_npm_versions(version: str) -> None:
    with pytest.raises(PackageError, match="Unable to determine npm version"):
        npm._require_supported_npm(version)


def test_get_npm_version(tmp_path: Path, monkeypatch) -> None:
    environment = {"PATH": "/usr/bin"}

    class Result:
        stdout = "11.19.0\n"

    def fake_run(command, check, capture_output, text, env):
        assert command == ["npm", "--version"]
        assert check is True
        assert capture_output is True
        assert text is True
        assert env is environment
        return Result()

    monkeypatch.setattr(npm.subprocess, "run", fake_run)

    assert npm._get_npm_version("npm", environment=environment) == "11.19.0"


def test_get_npm_version_reports_command_failure(monkeypatch) -> None:
    def fail(command, check, capture_output, text, env):
        raise subprocess.CalledProcessError(2, command)

    monkeypatch.setattr(npm.subprocess, "run", fail)

    with pytest.raises(PackageError, match="npm --version failed with exit code 2"):
        npm._get_npm_version("npm", environment={})


def test_get_npm_version_reports_execution_failure(monkeypatch) -> None:
    def fail(command, check, capture_output, text, env):
        raise OSError("permission denied")

    monkeypatch.setattr(npm.subprocess, "run", fail)

    with pytest.raises(
        PackageError,
        match="Unable to execute npm --version: permission denied",
    ):
        npm._get_npm_version("npm", environment={})


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


@pytest.mark.parametrize("allow_pack_scripts", [False, True])
@pytest.mark.parametrize("version", ["10.5.2", "10.9.9", "11.0.0-rc.0", "unknown"])
def test_npm_rejects_unsupported_runtime(
    tmp_path: Path, monkeypatch, version: str, allow_pack_scripts: bool
) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})
    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")
    monkeypatch.setattr(
        npm,
        "_get_npm_version",
        lambda *_args, **_kwargs: version,
    )

    def fail(*args, **kwargs):
        raise AssertionError("Unsupported npm must not pack or create credentials")

    monkeypatch.setattr(npm, "_run_npm", fail)
    monkeypatch.setattr(npm, "_write_temporary_npmrc", fail)
    monkeypatch.setattr(npm.tempfile, "TemporaryDirectory", fail)
    message = (
        "Unable to determine npm version"
        if version == "unknown"
        else "npm 11.0.0 or newer is required"
    )
    with pytest.raises(PackageError, match=message):
        npm.publish(
            client=FakeClient(),
            directory=package_dir,
            dry_run=False,
            allow_pack_scripts=allow_pack_scripts,
        )


def test_npm_reports_pack_failure(tmp_path: Path, monkeypatch) -> None:
    package_dir = tmp_path / "package"
    _write_package(package_dir, {"name": "example", "version": "1.0.0"})
    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")
    _mock_supported_npm(monkeypatch)

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
    _mock_supported_npm(monkeypatch)

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
    _mock_supported_npm(monkeypatch)

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
    _mock_supported_npm(monkeypatch)

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
    _mock_supported_npm(monkeypatch)

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


def test_read_package_json_reports_invalid_utf8(tmp_path: Path) -> None:
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "package.json").write_bytes(b"\xff")

    with pytest.raises(PackageError, match="Invalid UTF-8") as exc_info:
        npm.read_package_json(package_dir)

    assert isinstance(exc_info.value.__cause__, UnicodeDecodeError)
