import gzip
import io
import lzma
import tarfile
from pathlib import Path

import pytest
import zstandard

from forge_publish.errors import PackageError
from forge_publish.publishers.deb import read_deb_metadata


def _tar_control() -> bytes:
    control = b"Package: servcli\nVersion: 1.9.3-0\nArchitecture: i386\n"

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
