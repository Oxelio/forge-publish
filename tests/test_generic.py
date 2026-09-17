from pathlib import Path

import pytest

from forge_publish.config import Config
from forge_publish.errors import PackageError
from forge_publish.publishers import generic


class FakeClient:
    def __init__(self) -> None:
        self.config = Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
        )
        self.uploaded_url: str | None = None

    def upload(self, url: str, file: Path, dry_run: bool = False) -> None:
        self.uploaded_url = url


def test_generic_builds_expected_url(tmp_path: Path) -> None:
    package = tmp_path / "firmware.bin"
    package.write_bytes(b"data")
    client = FakeClient()

    generic.publish(
        client=client,
        file=package,
        package_name="firmware",
        version="1.2.3+build 1",
        filename="firmware-linux.bin",
    )

    assert client.uploaded_url == (
        "https://forge.example.com/api/packages/Software/generic/"
        "firmware/1.2.3%2Bbuild%201/firmware-linux.bin"
    )


def test_generic_rejects_invalid_package_name(tmp_path: Path) -> None:
    package = tmp_path / "firmware.bin"
    package.write_bytes(b"data")

    with pytest.raises(PackageError, match="Invalid package name"):
        generic.publish(
            client=FakeClient(),
            file=package,
            package_name="bad/name",
            version="1.0.0",
        )


@pytest.mark.parametrize(
    ("package_name", "version", "filename"),
    [
        (".", "1.0.0", "firmware.bin"),
        ("..", "1.0.0", "firmware.bin"),
        ("firmware", ".", "firmware.bin"),
        ("firmware", "..", "firmware.bin"),
        ("firmware", "1.0.0", "."),
        ("firmware", "1.0.0", ".."),
    ],
)
def test_generic_rejects_unsafe_path_segments(
    tmp_path: Path,
    package_name: str,
    version: str,
    filename: str,
) -> None:
    package = tmp_path / "firmware.bin"
    package.write_bytes(b"data")

    with pytest.raises(PackageError, match="Path traversal"):
        generic.publish(
            client=FakeClient(),
            file=package,
            package_name=package_name,
            version=version,
            filename=filename,
        )
