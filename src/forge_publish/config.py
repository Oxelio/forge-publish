from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from urllib.parse import urlsplit

import keyring
from keyring.errors import KeyringError

import tomllib

import tomli_w

from .errors import ConfigurationError


CONFIG_DIR = Path.home() / ".config" / "forge-publish"
CONFIG_FILE = CONFIG_DIR / "config.toml"
KEYRING_SERVICE = "forge-publish"
TOKEN_ENV_VAR = "FORGE_PUBLISH_TOKEN"


@dataclass
class Config:
    url: str
    owner: str
    username: str
    token: str | None = None

    @property
    def credential_name(self) -> str:
        return f"{self.url}|{self.owner}|{self.username}"

    def save(self) -> None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)

            with CONFIG_FILE.open("wb") as file:
                file.write(tomli_w.dumps(data).encode("utf-8"))
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to write configuration file: {CONFIG_FILE}"
            ) from exc

        data = {
            "url": self.url,
            "owner": self.owner,
            "username": self.username,
        }

        try:
            with CONFIG_FILE.open("wb") as file:
                file.write(tomli_w.dumps(data).encode("utf-8"))
        except OSError as exc:
            raise ConfigurationError(
                f"Unable to write configuration file: {CONFIG_FILE}"
            ) from exc

        try:
            CONFIG_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            # Permissions are best-effort and vary across platforms.
            pass


def _normalize_url(url: str) -> str:
    normalized = url.strip().rstrip("/")
    parsed = urlsplit(normalized)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ConfigurationError(
            "Forgejo URL must be a valid http:// or https:// URL."
        )

    return normalized


def _read_config_data() -> dict[str, object]:
    if not CONFIG_FILE.exists():
        raise ConfigurationError(
            f"Configuration file does not exist: {CONFIG_FILE}\n"
            "Run: forge-publish config"
        )

    try:
        with CONFIG_FILE.open("rb") as file:
            data = tomllib.load(file)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigurationError(
            f"Invalid TOML configuration: {CONFIG_FILE}"
        ) from exc
    except OSError as exc:
        raise ConfigurationError(
            f"Unable to read configuration file: {CONFIG_FILE}"
        ) from exc

    if not isinstance(data, dict):
        raise ConfigurationError("Invalid configuration format.")

    return data


def _build_config(data: dict[str, object]) -> Config:
    required = ("url", "owner", "username")
    missing = [
        field
        for field in required
        if not isinstance(data.get(field), str) or not str(data[field]).strip()
    ]

    if missing:
        raise ConfigurationError(
            "Missing configuration fields: " + ", ".join(missing)
        )

    return Config(
        url=_normalize_url(str(data["url"])),
        owner=str(data["owner"]).strip(),
        username=str(data["username"]).strip(),
    )


def _get_keyring_token(config: Config) -> str | None:
    try:
        return keyring.get_password(
            KEYRING_SERVICE,
            config.credential_name,
        )
    except KeyringError as exc:
        raise ConfigurationError(
            "Unable to read the Forgejo token from the system keyring."
        ) from exc


def _set_keyring_token(config: Config, token: str) -> None:
    try:
        keyring.set_password(
            KEYRING_SERVICE,
            config.credential_name,
            token,
        )
    except KeyringError as exc:
        raise ConfigurationError(
            "Unable to store the Forgejo token in the system keyring."
        ) from exc


def _prompt_token() -> str:
    try:
        token = getpass("Forgejo token: ").strip()
    except EOFError as exc:
        raise ConfigurationError(
            f"No Forgejo token available. Set {TOKEN_ENV_VAR} or run "
            "forge-publish config in an interactive terminal."
        ) from exc

    if not token:
        raise ConfigurationError("Forgejo token cannot be empty.")

    return token


def load_config(*, require_token: bool = True) -> Config:
    data = _read_config_data()
    config = _build_config(data)

    if not require_token:
        return config

    token = os.environ.get(TOKEN_ENV_VAR)
    if not token:
        token = _get_keyring_token(config)
    if not token:
        token = _prompt_token()

    config.token = token
    return config


def configure(
    url: str,
    owner: str,
    username: str,
) -> None:
    config = Config(
        url=_normalize_url(url),
        owner=owner.strip(),
        username=username.strip(),
    )

    if not config.owner:
        raise ConfigurationError("Forgejo owner cannot be empty.")
    if not config.username:
        raise ConfigurationError("Forgejo username cannot be empty.")

    token = _prompt_token()
    _set_keyring_token(config, token)
    config.save()

    print(f"Configuration saved to {CONFIG_FILE}")
    print("Forgejo token stored in the system keyring.")
