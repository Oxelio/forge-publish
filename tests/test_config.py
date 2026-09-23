from pathlib import Path

import pytest
from keyring.errors import KeyringError

from forge_publish import config as config_module
from forge_publish.errors import ConfigurationError


@pytest.mark.parametrize(
    "url",
    [
        "https://forge.example.com?foo=bar",
        "https://forge.example.com#fragment",
        "https://forge.example.com?",
        "https://forge.example.com#",
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
        lambda *_: "keyring-token",
    )

    config = config_module.load_config(require_token=True)

    assert config.token == "env-token"


def test_keyring_token_is_used_when_environment_token_is_absent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        'url = "https://forge.example.com"\nowner = "Software"\nusername = "user"\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.delenv("FORGE_PUBLISH_TOKEN", raising=False)
    monkeypatch.setattr(
        config_module.keyring,
        "get_password",
        lambda *_: "keyring-token",
    )

    config = config_module.load_config(require_token=True)

    assert config.token == "keyring-token"


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

    def fail(*_):
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


def test_config_credential_name_contains_connection_identity() -> None:
    config = config_module.Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
    )

    assert config.credential_name == "https://forge.example.com|Software|user"


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


def test_config_save_reports_write_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    class BrokenConfigFile:
        def open(self, *args, **kwargs):
            raise OSError("read-only filesystem")

        def __str__(self) -> str:
            return "broken-config.toml"

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", BrokenConfigFile())

    config = config_module.Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
    )

    with pytest.raises(ConfigurationError, match="Unable to write configuration file"):
        config.save()


def test_config_save_ignores_chmod_error(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"

    class ConfigFile:
        def open(self, *args, **kwargs):
            return config_file.open(*args, **kwargs)

        def chmod(self, *args, **kwargs):
            raise OSError("chmod unsupported")

        def __str__(self) -> str:
            return str(config_file)

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", ConfigFile())

    config_module.Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
    ).save()

    assert config_file.exists()


def test_keyring_error_falls_back_to_prompt(
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
    monkeypatch.delenv("FORGE_PUBLISH_TOKEN", raising=False)

    def fail(*_):
        raise KeyringError("keyring unavailable")

    monkeypatch.setattr(
        config_module.keyring,
        "get_password",
        fail,
    )
    monkeypatch.setattr(
        config_module,
        "_prompt_token",
        lambda: "prompt-token",
    )

    config = config_module.load_config(require_token=True)

    assert config.token == "prompt-token"


@pytest.mark.parametrize(
    "owner",
    [
        "",
        "   ",
        ".",
        "..",
    ],
)
def test_rejects_unsafe_owner(owner: str) -> None:
    with pytest.raises(ConfigurationError, match="owner"):
        config_module._normalize_owner(owner)


@pytest.mark.parametrize(
    "url",
    [
        "http://forge.example.com",
        "https://user:password@forge.example.com",
        "https://forge.example.com:abc",
        "https://forge.example.com:99999",
        "https://forge.example.com/bad path",
    ],
)
def test_rejects_invalid_url(url: str) -> None:
    with pytest.raises(ConfigurationError):
        config_module._normalize_url(url)


def test_read_config_reports_missing_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(config_module, "CONFIG_FILE", tmp_path / "missing.toml")

    with pytest.raises(ConfigurationError, match="does not exist"):
        config_module._read_config_data()


def test_read_config_reports_invalid_toml(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"
    config_file.write_text('url = "unterminated', encoding="utf-8")
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)

    with pytest.raises(ConfigurationError, match="Invalid TOML"):
        config_module._read_config_data()


def test_read_config_reports_io_error(
    monkeypatch,
) -> None:
    class BrokenConfigFile:
        def exists(self) -> bool:
            return True

        def open(self, *args, **kwargs):
            raise OSError("read failed")

        def __str__(self) -> str:
            return "broken-config.toml"

    monkeypatch.setattr(config_module, "CONFIG_FILE", BrokenConfigFile())

    with pytest.raises(ConfigurationError, match="Unable to read configuration file"):
        config_module._read_config_data()


def test_build_config_reports_missing_fields() -> None:
    with pytest.raises(ConfigurationError, match="owner, username"):
        config_module._build_config(
            {
                "url": "https://forge.example.com",
                "owner": "",
            }
        )


def test_set_keyring_token_reports_backend_error(monkeypatch) -> None:
    config = config_module.Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
    )

    def fail(*args, **kwargs):
        raise KeyringError("backend unavailable")

    monkeypatch.setattr(config_module.keyring, "set_password", fail)

    with pytest.raises(ConfigurationError, match="Unable to store"):
        config_module._set_keyring_token(config, "token")


def test_prompt_token_reports_non_interactive_input(monkeypatch) -> None:
    def fail(_):
        raise EOFError

    monkeypatch.setattr(config_module, "getpass", fail)

    with pytest.raises(ConfigurationError, match="No Forgejo token available"):
        config_module._prompt_token()


def test_prompt_token_rejects_empty_value(monkeypatch) -> None:
    monkeypatch.setattr(config_module, "getpass", lambda _: "   ")

    with pytest.raises(ConfigurationError, match="cannot be empty"):
        config_module._prompt_token()


def test_configure_rejects_empty_username() -> None:
    with pytest.raises(ConfigurationError, match="username"):
        config_module.configure(
            url="https://forge.example.com",
            owner="Software",
            username="   ",
        )


def test_configure_does_not_use_keyring_with_environment_token(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.setenv("FORGE_PUBLISH_TOKEN", "env-token")

    def fail(*_):
        raise AssertionError("keyring should not be accessed")

    monkeypatch.setattr(
        config_module,
        "_set_keyring_token",
        fail,
    )
    monkeypatch.setattr(
        config_module,
        "_prompt_token",
        fail,
    )

    config_module.configure(
        url="https://forge.example.com",
        owner="Software",
        username="user",
    )

    assert config_file.exists()


def test_configure_stores_prompted_token_in_keyring(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "config.toml"
    captured: dict[str, object] = {}

    monkeypatch.setattr(config_module, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_module, "CONFIG_FILE", config_file)
    monkeypatch.delenv("FORGE_PUBLISH_TOKEN", raising=False)
    monkeypatch.setattr(config_module, "_prompt_token", lambda: "prompt-token")

    def capture(config, token):
        captured["credential_name"] = config.credential_name
        captured["token"] = token

    monkeypatch.setattr(config_module, "_set_keyring_token", capture)

    config_module.configure(
        url="https://forge.example.com/",
        owner=" Software ",
        username=" user ",
    )

    assert captured == {
        "credential_name": "https://forge.example.com|Software|user",
        "token": "prompt-token",
    }
    assert config_file.exists()
