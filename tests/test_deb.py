import gzip
import io
import lzma
import tarfile
from pathlib import Path

import pytest
import zstandard

from forge_publish.config import Config
from forge_publish.errors import PackageError
from forge_publish.publishers.deb import publish, read_deb_metadata


class FakeClient:
    def __init__(self) -> None:
        self.config = Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
        )

    def upload(
        self,
        url: str,
        file: Path,
        dry_run: bool = False,
    ) -> None:
        raise AssertionError("upload should not be called")


def _tar_control(
    control: bytes = (b"Package: servcli\nVersion: 1.9.3-0\nArchitecture: i386\n"),
) -> bytes:
    output = io.BytesIO()

    with tarfile.open(fileobj=output, mode="w") as archive:
        info = tarfile.TarInfo("control")
        info.size = len(control)
        archive.addfile(info, io.BytesIO(control))

    return output.getvalue()


def _ar_member(name: str, data: bytes) -> bytes:
    header = (
        f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{0o100644:<8o}{len(data):<10}`\n"
    ).encode("ascii")
    padding = b"\n" if len(data) % 2 else b""
    return header + data + padding


def _write_deb(path: Path, control_name: str, control_data: bytes) -> None:
    path.write_bytes(
        b"!<arch>\n"
        + _ar_member("debian-binary", b"2.0\n")
        + _ar_member(control_name, control_data)
        + _ar_member("data.tar.gz", gzip.compress(b"payload"))
    )


@pytest.mark.parametrize(
    ("name", "compress"),
    [
        ("control.tar", lambda data: data),
        ("control.tar.gz", gzip.compress),
        ("control.tar.xz", lzma.compress),
        (
            "control.tar.zst",
            lambda data: zstandard.ZstdCompressor().compress(data),
        ),
    ],
)
def test_read_deb_metadata(
    tmp_path: Path,
    name: str,
    compress,
) -> None:
    package = tmp_path / "servcli.deb"
    _write_deb(package, name, compress(_tar_control()))

    metadata = read_deb_metadata(package)

    assert metadata == {
        "name": "servcli",
        "version": "1.9.3-0",
        "architecture": "i386",
    }


def test_rejects_invalid_debian_binary(tmp_path: Path) -> None:
    package = tmp_path / "invalid.deb"
    package.write_bytes(
        b"!<arch>\n"
        + _ar_member("debian-binary", b"1.0\n")
        + _ar_member("control.tar", _tar_control())
    )

    with pytest.raises(PackageError, match="debian-binary"):
        read_deb_metadata(package)


def test_read_deb_metadata_accepts_case_insensitive_fields(
    tmp_path: Path,
) -> None:
    package = tmp_path / "servcli.deb"

    control = b"package: servcli\nVERSION: 1.9.3-0\nArChiTecTure: i386\n"

    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(_tar_control(control)),
    )

    metadata = read_deb_metadata(package)

    assert metadata == {
        "name": "servcli",
        "version": "1.9.3-0",
        "architecture": "i386",
    }


@pytest.mark.parametrize(
    ("distribution", "component"),
    [
        (".", "main"),
        ("..", "main"),
        ("stable", "."),
        ("stable", ".."),
    ],
)
def test_debian_publish_rejects_unsafe_path_segments(
    tmp_path: Path,
    distribution: str,
    component: str,
) -> None:
    package = tmp_path / "servcli.deb"

    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(_tar_control()),
    )

    with pytest.raises(PackageError, match="Path traversal"):
        publish(
            client=FakeClient(),
            file=package,
            distribution=distribution,
            component=component,
        )
