from pathlib import Path

import pytest

from forge_publish import config as config_module
from forge_publish.errors import ConfigurationError


@pytest.mark.parametrize(
    "url",
    [
        "https://forge.example.com?foo=bar",
        "https://forge.example.com#fragment",
    ],
)
def test_rejects_url_query_and_fragment(url: str) -> None:
    with pytest.raises(ConfigurationError):
        config_module._normalize_url(url)


def test_environment_token_has_priority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'url = "https://forge.example.com"\nowner = "Software"\nusername = "user"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.setenv("FORGE_PUBLISH_TOKEN", "env-token")
    monkeypatch.setattr(
        config_module.keyring,
        "get_password",
        lambda *args: "keyring-token",
    )

    config = config_module.load_config()

    assert config.token == "env-token"


def test_load_config_without_token_does_not_access_keyring(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'url = "https://forge.example.com"\nowner = "Software"\nusername = "user"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    def fail(*args):
        raise AssertionError("keyring should not be accessed")

    monkeypatch.setattr(config_module.keyring, "get_password", fail)

    config = config_module.load_config(require_token=False)

    assert config.token is None


def test_config_repr_does_not_expose_token() -> None:
    config = config_module.Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
        token="secret-token",
    )

    assert "secret-token" not in repr(config)


def test_config_save_writes_configuration(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"

    monkeypatch.setattr(
        config_module,
        "CONFIG_DIR",
        tmp_path,
    )
    monkeypatch.setattr(
        config_module,
        "CONFIG_FILE",
        config_file,
    )

    config = config_module.Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
        token="secret-token",
    )

    config.save()

    content = config_file.read_text(encoding="utf-8")

    assert 'url = "https://forge.example.com"' in content
    assert 'owner = "Software"' in content
    assert 'username = "user"' in content
    assert "secret-token" not in content
