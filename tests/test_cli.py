from pathlib import Path

import pytest
from click.testing import CliRunner

from forge_publish import cli
from forge_publish import config as config_module
from forge_publish.cli import main
from forge_publish.config import Config


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
def test_generic_redirect_is_reported_without_success(
    tmp_path: Path, monkeypatch, redirect_session, status_code: int
) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"private package data")
    config = Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
        token="secret",
    )
    monkeypatch.setattr(cli, "load_config", lambda *, require_token: config)
    session, adapter = redirect_session(status_code)
    monkeypatch.setattr("forge_publish.client.requests.Session", lambda: session)

    result = CliRunner().invoke(
        main,
        ["generic", str(package), "--package", "example", "--version", "1.0.0"],
    )

    assert result.exit_code == 1
    assert f"Error: HTTP {status_code}:" in result.output
    assert "canonical Forgejo URL" in result.output
    assert "published successfully" not in result.output
    assert "Traceback" not in result.output
    assert len(adapter.requests) == 1
    assert adapter.requests[0][0] == "PUT"


def test_create_client_does_not_warn_when_insecure_dry_run(
    monkeypatch,
    capsys,
) -> None:
    config = Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
    )

    monkeypatch.setattr(
        cli,
        "load_config",
        lambda *, require_token: config,
    )

    client = cli._create_client(
        dry_run=True,
        insecure=True,
    )

    captured = capsys.readouterr()

    assert captured.err == ""
    assert client.verify_tls is False


def test_create_client_warns_when_tls_verification_is_disabled(
    monkeypatch,
    capsys,
) -> None:
    config = Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
        token="secret",
    )

    monkeypatch.setattr(
        cli,
        "load_config",
        lambda *, require_token: config,
    )

    client = cli._create_client(
        dry_run=False,
        insecure=True,
    )

    captured = capsys.readouterr()

    assert captured.err == ("WARNING: TLS certificate verification is disabled.\n")
    assert client.verify_tls is False


def test_generic_command_passes_insecure_to_client(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")

    captured: dict[str, bool] = {}
    client = object()

    def create_client(
        *,
        dry_run: bool,
        insecure: bool,
    ):
        captured["dry_run"] = dry_run
        captured["insecure"] = insecure
        return client

    monkeypatch.setattr(
        cli,
        "_create_client",
        create_client,
    )
    monkeypatch.setattr(
        cli.generic,
        "publish",
        lambda **kwargs: None,
    )

    result = CliRunner().invoke(
        main,
        [
            "generic",
            str(package),
            "--package",
            "example",
            "--version",
            "1.0.0",
            "--insecure",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured == {
        "dry_run": False,
        "insecure": True,
    }


def test_deb_command_passes_insecure_to_client(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = tmp_path / "package.deb"
    package.write_bytes(b"data")

    captured: dict[str, bool] = {}
    client = object()

    def create_client(
        *,
        dry_run: bool,
        insecure: bool,
    ):
        captured["dry_run"] = dry_run
        captured["insecure"] = insecure
        return client

    monkeypatch.setattr(
        cli,
        "_create_client",
        create_client,
    )
    monkeypatch.setattr(
        cli.deb,
        "publish",
        lambda **kwargs: None,
    )

    result = CliRunner().invoke(
        main,
        [
            "deb",
            str(package),
            "--distribution",
            "lenny",
            "--component",
            "main",
            "--insecure",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured == {
        "dry_run": False,
        "insecure": True,
    }


def test_deb_requires_distribution(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package.deb"
    package.write_bytes(b"data")

    result = CliRunner().invoke(
        main,
        [
            "deb",
            str(package),
            "--component",
            "main",
        ],
    )

    assert result.exit_code != 0
    assert "Missing option '--distribution'" in result.output


def test_deb_requires_component(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package.deb"
    package.write_bytes(b"data")

    result = CliRunner().invoke(
        main,
        [
            "deb",
            str(package),
            "--distribution",
            "lenny",
        ],
    )

    assert result.exit_code != 0
    assert "Missing option '--component'" in result.output


def test_generic_command_passes_none_when_filename_is_omitted(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")

    captured: dict[str, object] = {}
    client = object()

    monkeypatch.setattr(
        cli,
        "_create_client",
        lambda *, dry_run, insecure: client,
    )

    def publish(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        cli.generic,
        "publish",
        publish,
    )

    result = CliRunner().invoke(
        main,
        [
            "generic",
            str(package),
            "--package",
            "example",
            "--version",
            "1.0.0",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["filename"] is None


def test_npm_uses_current_directory_by_default(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    client = object()

    monkeypatch.setattr(
        cli,
        "_create_client",
        lambda *, dry_run, insecure: client,
    )

    def publish(**kwargs) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(
        cli.npm,
        "publish",
        publish,
    )

    result = CliRunner().invoke(
        main,
        ["npm"],
    )

    assert result.exit_code == 0, result.output
    assert captured["directory"] == Path(".")


def test_npm_invalid_utf8_is_reported_without_traceback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "package.json").write_bytes(b"\xff")

    monkeypatch.setattr(
        cli,
        "_create_client",
        lambda *, dry_run, insecure: object(),
    )

    result = CliRunner().invoke(
        main,
        ["npm", str(package_dir), "--dry-run"],
    )

    assert result.exit_code != 0
    assert "Error: Invalid UTF-8" in result.output
    assert "Traceback" not in result.output


def test_config_invalid_utf8_is_reported_without_traceback(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_bytes(b"\xff")
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    package = tmp_path / "package.bin"
    package.write_bytes(b"data")

    result = CliRunner().invoke(
        main,
        [
            "generic",
            str(package),
            "--package",
            "example",
            "--version",
            "1.0.0",
            "--dry-run",
        ],
    )

    assert result.exit_code != 0
    assert "Error: Invalid UTF-8 configuration:" in result.output
    assert "Traceback" not in result.output


@pytest.mark.parametrize(
    "url",
    [
        "https://[::1",
        "https://::1]",
        "https://forge.example.com\uff0fpath",
        "https://forge.example.com\uff1a443",
    ],
)
@pytest.mark.parametrize("command", ["config", "generic", "generic-dry-run"])
def test_url_parser_errors_are_reported_before_side_effects(
    tmp_path: Path, monkeypatch, url: str, command: str
) -> None:
    config_dir = tmp_path / "configuration"
    config_file = config_dir / "config.toml"
    monkeypatch.setattr(config_module, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.delenv("FORGE_PUBLISH_TOKEN", raising=False)

    def fail(*args, **kwargs):
        raise AssertionError("invalid URL must be rejected before side effects")

    monkeypatch.setattr(config_module, "_prompt_token", fail)
    monkeypatch.setattr(config_module.keyring, "get_password", fail)
    monkeypatch.setattr(config_module.keyring, "set_password", fail)
    monkeypatch.setattr(config_module.Config, "save", fail)
    monkeypatch.setattr("forge_publish.client.requests.Session", fail)
    monkeypatch.setattr(cli.generic, "publish", fail)

    if command == "config":
        args = ["config", "--url", url, "--owner", "Software", "--username", "user"]
    else:
        config_dir.mkdir()
        config_file.write_text(
            f'url = "{url}"\nowner = "Software"\nusername = "user"\n',
            encoding="utf-8",
        )
        original_config = config_file.read_bytes()
        package = tmp_path / "package.bin"
        package.write_bytes(b"data")
        args = ["generic", str(package), "--package", "example", "--version", "1.0.0"]
        if command == "generic-dry-run":
            args.append("--dry-run")

    result = CliRunner().invoke(main, args)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.output == (
        "Error: Forgejo URL must be a valid HTTPS URL without "
        "credentials, query parameters, or fragments.\n"
    )
    if command == "config":
        assert not config_dir.exists()
    else:
        assert config_file.read_bytes() == original_config
