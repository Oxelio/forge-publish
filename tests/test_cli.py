from pathlib import Path

from click.testing import CliRunner

from forge_publish import cli
from forge_publish.cli import main
from forge_publish.config import Config


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
