from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path

import tomllib
import tomli_w


CONFIG_DIR = Path.home() / ".config" / "forge-publish"
CONFIG_FILE = CONFIG_DIR / "config.toml"


@dataclass
class Config:
    url: str
    owner: str
    username: str
    token: str | None = None

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "url": self.url,
            "owner": self.owner,
            "username": self.username,
        }

        if self.token:
            data["token"] = self.token

        with CONFIG_FILE.open("wb") as f:
            f.write(tomli_w.dumps(data).encode())

        CONFIG_FILE.chmod(
            stat.S_IRUSR | stat.S_IWUSR
        )


def load_config() -> Config:
    if not CONFIG_FILE.exists():
        raise RuntimeError(
            f"Configuration file does not exist: {CONFIG_FILE}\n"
            "Run: forge-publish config"
        )

    with CONFIG_FILE.open("rb") as f:
        data = tomllib.load(f)

    token = data.get("token") or os.environ.get("FORGE_PUBLISH_TOKEN")

    if not token:
        token = getpass("Forgejo token: ")

    return Config(
        url=data["url"].rstrip("/"),
        owner=data["owner"],
        username=data["username"],
        token=token,
    )


def configure(
    url: str,
    owner: str,
    username: str,
) -> None:
    token = getpass("Forgejo token: ")

    config = Config(
        url=url.rstrip("/"),
        owner=owner,
        username=username,
        token=token,
    )

    config.save()

    print(f"Configuration saved to {CONFIG_FILE}")