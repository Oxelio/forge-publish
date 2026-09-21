from pathlib import Path

import pytest
import requests

from forge_publish.client import REQUEST_TIMEOUT, ForgejoClient, ForgejoError
from forge_publish.config import Config


class FailingSession:
    def __init__(self) -> None:
        self.auth = None

    def put(self, url, data, timeout):
        raise requests.ConnectionError("connection failed")


class Response:
    status_code = 201
    text = ""

    def json(self):
        raise ValueError


class Session:
    def __init__(self) -> None:
        self.auth = None
        self.timeout = None

    def put(self, url, data, timeout):
        self.timeout = timeout
        return Response()


def test_dry_run_does_not_require_token(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")
    client = ForgejoClient(
        Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
        )
    )

    client.upload(
        "https://forge.example.com/upload",
        package,
        dry_run=True,
    )


def test_upload_uses_timeout(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")
    client = ForgejoClient(
        Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
            token="secret",
        )
    )
    session = Session()
    client.session = session

    client.upload("https://forge.example.com/upload", package)

    assert session.timeout == REQUEST_TIMEOUT


def test_upload_reports_network_error(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")

    client = ForgejoClient(
        Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
            token="secret",
        )
    )
    client.session = FailingSession()

    with pytest.raises(
        ForgejoError,
        match="HTTP request failed: connection failed",
    ):
        client.upload(
            "https://forge.example.com/upload",
            package,
        )
