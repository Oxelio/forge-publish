from pathlib import Path

import pytest
import requests

from forge_publish.client import REQUEST_TIMEOUT, ForgejoClient, ForgejoError
from forge_publish.config import Config


class FailingSession:
    def __init__(self) -> None:
        self.auth = None

    def put(self, url, data, timeout, verify):
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
        self.verify = None

    def put(self, url, data, timeout, verify):
        self.timeout = timeout
        self.verify = verify
        return Response()

    def delete(self, url, timeout, verify):
        self.timeout = timeout
        self.verify = verify
        return Response()


def test_dry_run_does_not_require_token(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")
    client = ForgejoClient(
        Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
        ),
        verify_tls=True,
    )

    client.upload(
        url="https://forge.example.com/upload",
        file=package,
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
        ),
        verify_tls=True,
    )

    session = Session()
    client.session = session

    client.upload(
        url="https://forge.example.com/upload",
        file=package,
        dry_run=False,
    )

    assert session.timeout == REQUEST_TIMEOUT
    assert session.verify is True


def test_upload_reports_network_error(tmp_path: Path) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")

    client = ForgejoClient(
        Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
            token="secret",
        ),
        verify_tls=True,
    )
    client.session = FailingSession()

    with pytest.raises(
        ForgejoError,
        match="HTTP request failed: connection failed",
    ):
        client.upload(
            url="https://forge.example.com/upload",
            file=package,
            dry_run=False,
        )


def test_upload_disables_tls_verification(
    tmp_path: Path,
) -> None:
    package = tmp_path / "package.bin"
    package.write_bytes(b"data")

    client = ForgejoClient(
        Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
            token="secret",
        ),
        verify_tls=False,
    )

    session = Session()
    client.session = session

    client.upload(
        url="https://forge.example.com/upload",
        file=package,
        dry_run=False,
    )

    assert session.verify is False


def test_delete_disables_tls_verification() -> None:
    client = ForgejoClient(
        Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
            token="secret",
        ),
        verify_tls=False,
    )

    session = Session()
    client.session = session

    client.delete(
        url="https://forge.example.com/package",
        dry_run=False,
        ignore_404=False,
    )

    assert session.verify is False
