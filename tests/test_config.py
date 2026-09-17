from pathlib import Path

from forge_publish import config as config_module


def test_environment_token_has_priority(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'url = "https://forge.example.com"\n'
        'owner = "Software"\n'
        'username = "user"\n',
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
        'url = "https://forge.example.com"\n'
        'owner = "Software"\n'
        'username = "user"\n',
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
