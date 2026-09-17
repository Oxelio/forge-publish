from pathlib import Path

from forge_publish.client import REQUEST_TIMEOUT, ForgejoClient
from forge_publish.config import Config


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
