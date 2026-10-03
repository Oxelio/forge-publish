import bz2
import gzip
import io
import lzma
import tarfile
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import zstandard
from click.testing import CliRunner

from forge_publish import config as config_module
from forge_publish.cli import main
from forge_publish.config import Config
from forge_publish.errors import PackageError
from forge_publish.publishers import deb as deb_module
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
        *,
        dry_run: bool,
    ) -> None:
        raise AssertionError("upload should not be called")


class RecordingClient:
    def __init__(self) -> None:
        self.config = Config(
            url="https://forge.example.com",
            owner="Software Team",
            username="user",
        )
        self.uploaded_url: str | None = None
        self.uploaded_file: Path | None = None
        self.dry_run: bool | None = None

    def upload(
        self,
        url: str,
        file: Path,
        *,
        dry_run: bool,
    ) -> None:
        self.uploaded_url = url
        self.uploaded_file = file
        self.dry_run = dry_run


def _tar_control(
    control: bytes = (b"Package: servcli\nVersion: 1.9.3-0\nArchitecture: i386\n"),
) -> bytes:
    output = io.BytesIO()

    with tarfile.open(fileobj=output, mode="w") as archive:
        info = tarfile.TarInfo("control")
        info.size = len(control)
        archive.addfile(info, io.BytesIO(control))

    return output.getvalue()


def _tar_without_control() -> bytes:
    output = io.BytesIO()

    with tarfile.open(fileobj=output, mode="w") as archive:
        data = b"metadata"
        info = tarfile.TarInfo("metadata")
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))

    return output.getvalue()


def _ar_member(name: str, data: bytes) -> bytes:
    if len(name) > 16:
        raise ValueError("ar member name is too long")

    member_name = f"{name}/" if len(name) < 16 else name

    header = (
        f"{member_name:<16}{0:<12}{0:<6}{0:<6}{0o100644:<8o}{len(data):<10}`\n"
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
        ("control.tar.bz2", bz2.compress),
        (
            "control.tar.lzma",
            lambda data: lzma.compress(data, format=lzma.FORMAT_ALONE),
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


def test_rejects_invalid_debian_magic(tmp_path: Path) -> None:
    package = tmp_path / "invalid.deb"
    package.write_bytes(b"not-an-ar-archive")

    with pytest.raises(PackageError, match="not a valid Debian package"):
        read_deb_metadata(package)


def test_rejects_truncated_ar_header(tmp_path: Path) -> None:
    package = tmp_path / "invalid.deb"
    package.write_bytes(b"!<arch>\nshort")

    with pytest.raises(PackageError, match="truncated ar archive"):
        read_deb_metadata(package)


def test_rejects_invalid_ar_header_trailer(tmp_path: Path) -> None:
    member = bytearray(_ar_member("debian-binary", b"2.0\n"))
    member[58:60] = b"??"
    package = tmp_path / "invalid.deb"
    package.write_bytes(b"!<arch>\n" + bytes(member))

    with pytest.raises(PackageError, match="invalid ar header"):
        read_deb_metadata(package)


def test_rejects_invalid_debian_binary(tmp_path: Path) -> None:
    package = tmp_path / "invalid.deb"
    package.write_bytes(
        b"!<arch>\n"
        + _ar_member("debian-binary", b"1.0\n")
        + _ar_member("control.tar", _tar_control())
    )

    with pytest.raises(PackageError, match="debian-binary"):
        read_deb_metadata(package)


@pytest.mark.parametrize("size", [17, 4096, 9999999999])
def test_rejects_oversized_debian_binary_before_reading(size: int) -> None:
    header = bytearray(_ar_member("debian-binary", b"")[:60])
    header[48:58] = f"{size:<10}".encode("ascii")
    read_sizes: list[int] = []

    class ReadSpy(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            if size < 0 or size > 60:
                raise AssertionError("unbounded marker read requested")
            return super().read(size)

    stream = ReadSpy(b"!<arch>\n" + bytes(header))
    package = Mock(spec=Path)
    package.name = "oversized.deb"
    package.open.return_value = stream

    with pytest.raises(PackageError, match="debian-binary member is too large"):
        read_deb_metadata(package)

    assert read_sizes == [8, 60]


def test_rejects_oversized_whitespace_padded_debian_binary(tmp_path: Path) -> None:
    package = tmp_path / "oversized.deb"
    package.write_bytes(
        b"!<arch>\n"
        + _ar_member("debian-binary", b"2.0" + b" " * 4093)
        + _ar_member("control.tar", _tar_control())
    )

    with pytest.raises(PackageError, match="debian-binary member is too large"):
        publish(
            client=FakeClient(),
            file=package,
            distribution="stable",
            component="main",
            dry_run=False,
        )


@pytest.mark.parametrize("marker", [b"2.0", b"2.0\n", b" 2.0\r\n", b"2.0" + b" " * 13])
def test_read_deb_metadata_accepts_bounded_debian_binary(
    tmp_path: Path,
    marker: bytes,
) -> None:
    package = tmp_path / "servcli.deb"
    package.write_bytes(
        b"!<arch>\n"
        + _ar_member("debian-binary", marker)
        + _ar_member("control.tar", _tar_control())
    )

    assert read_deb_metadata(package) == {
        "name": "servcli",
        "version": "1.9.3-0",
        "architecture": "i386",
    }


def test_large_data_member_is_skipped_without_reading() -> None:
    size = 9999999999
    data_header = bytearray(_ar_member("data.tar.gz", b"")[:60])
    data_header[48:58] = f"{size:<10}".encode("ascii")
    control = _tar_control()
    # Model a large data member without allocating its payload or a sparse file.
    stream = Mock()
    stream.read.side_effect = [
        b"!<arch>\n",
        _ar_member("debian-binary", b"2.0\n")[:60],
        b"2.0\n",
        bytes(data_header),
        b"\n",
        _ar_member("control.tar", control)[:60],
        control,
    ]
    package = Mock(spec=Path)
    package.name = "large-data.deb"
    package.open.return_value = MagicMock()
    package.open.return_value.__enter__.return_value = stream

    assert deb_module._read_control_archive(package) == ("control.tar", control)
    stream.seek.assert_called_once_with(size, 1)
    assert [call.args[0] for call in stream.read.call_args_list] == [
        8,
        60,
        4,
        60,
        1,
        60,
        len(control),
    ]


@pytest.mark.parametrize("marker", [b"2.0" + b" " * 4093, b"1.0\n", b"2."])
def test_debian_binary_error_is_reported_by_cli_dry_run(
    tmp_path: Path,
    monkeypatch,
    marker: bytes,
) -> None:
    package = tmp_path / "invalid.deb"
    member = _ar_member("debian-binary", marker)
    if marker == b"2.":
        # Declare four bytes but supply only two to exercise truncation.
        member = _ar_member("debian-binary", b"2.0\n")[:60] + marker
    else:
        member += _ar_member("control.tar", _tar_control())
    package.write_bytes(b"!<arch>\n" + member)
    monkeypatch.setattr(
        config_module,
        "_read_config_data",
        lambda: {
            "url": "https://forge.example.com",
            "owner": "Software",
            "username": "user",
        },
    )

    def unexpected_call(*args, **kwargs):
        raise AssertionError("dry-run must not access tokens or upload")

    monkeypatch.setattr(config_module, "_get_keyring_token", unexpected_call)
    monkeypatch.setattr(config_module, "_prompt_token", unexpected_call)
    monkeypatch.setattr(deb_module.ForgejoClient, "upload", unexpected_call)
    monkeypatch.setattr("requests.sessions.Session.request", unexpected_call)

    result = CliRunner().invoke(
        main,
        [
            "deb",
            str(package),
            "--distribution",
            "stable",
            "--component",
            "main",
            "--dry-run",
        ],
    )

    assert result.exit_code == 1
    assert result.output.startswith("Error: ")
    if len(marker) > 16:
        assert "debian-binary member is too large" in result.output
    elif marker == b"2.":
        assert "truncated ar member" in result.output
    else:
        assert "valid debian-binary member" in result.output
    assert "Traceback" not in result.output
    assert "published" not in result.output.lower()
    assert "Token" not in result.output


def test_rejects_missing_control_archive(tmp_path: Path) -> None:
    package = tmp_path / "invalid.deb"
    package.write_bytes(
        b"!<arch>\n"
        + _ar_member("debian-binary", b"2.0\n")
        + _ar_member("data.tar.gz", gzip.compress(b"payload"))
    )

    with pytest.raises(PackageError, match="does not contain a control archive"):
        read_deb_metadata(package)


def test_rejects_oversized_compressed_control_archive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = tmp_path / "oversized.deb"
    compressed = gzip.compress(_tar_control())

    monkeypatch.setattr(
        deb_module,
        "MAX_CONTROL_ARCHIVE_COMPRESSED_SIZE",
        len(compressed) - 1,
    )
    _write_deb(package, "control.tar.gz", compressed)

    with pytest.raises(PackageError, match="control archive is too large"):
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
    ("distribution", "component", "message"),
    [
        (".", "main", "Path traversal"),
        ("..", "main", "Path traversal"),
        ("stable", ".", "Path traversal"),
        ("stable", "..", "Path traversal"),
        ("", "main", "non-empty"),
        (" stable", "main", "leading or trailing"),
        ("stable", " main ", "leading or trailing"),
    ],
)
def test_debian_publish_rejects_invalid_path_segments(
    tmp_path: Path,
    distribution: str,
    component: str,
    message: str,
) -> None:
    package = tmp_path / "servcli.deb"

    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(_tar_control()),
    )

    with pytest.raises(PackageError, match=message):
        publish(
            client=FakeClient(),
            file=package,
            distribution=distribution,
            component=component,
            dry_run=False,
        )


def test_rejects_oversized_decompressed_control_archive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = tmp_path / "oversized.deb"

    monkeypatch.setattr(
        deb_module,
        "MAX_CONTROL_ARCHIVE_SIZE",
        128,
    )

    oversized = b"x" * 1024

    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(oversized),
    )

    with pytest.raises(PackageError, match="too large"):
        read_deb_metadata(package)


def test_rejects_oversized_uncompressed_control_archive(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = tmp_path / "oversized.deb"
    control_tar = _tar_control()

    monkeypatch.setattr(
        deb_module,
        "MAX_CONTROL_ARCHIVE_SIZE",
        len(control_tar) - 1,
    )

    _write_deb(package, "control.tar", control_tar)

    with pytest.raises(PackageError, match="too large"):
        read_deb_metadata(package)


def test_rejects_unsupported_control_archive(tmp_path: Path) -> None:
    package = tmp_path / "unsupported.deb"
    _write_deb(package, "control.tar.zip", b"not-supported")

    with pytest.raises(PackageError, match="Unsupported control archive format"):
        read_deb_metadata(package)


def test_rejects_invalid_compressed_control_archive(tmp_path: Path) -> None:
    package = tmp_path / "invalid-compression.deb"
    _write_deb(package, "control.tar.gz", b"not-gzip")

    with pytest.raises(PackageError, match="Unable to decompress"):
        read_deb_metadata(package)


@pytest.mark.parametrize(
    "control",
    [
        b"Package servcli\nVersion: 1.9.3-0\nArchitecture: i386\n",
        (
            b"Package: servcli\n"
            b"Package: duplicate\n"
            b"Version: 1.9.3-0\n"
            b"Architecture: i386\n"
        ),
        (b"Package: servcli\n\nVersion: 1.9.3-0\nArchitecture: i386\n"),
        b" continuation-without-field\n",
        (b"Package Name: servcli\nVersion: 1.9.3-0\nArchitecture: i386\n"),
    ],
)
def test_rejects_malformed_debian_control(
    tmp_path: Path,
    control: bytes,
) -> None:
    package = tmp_path / "invalid-control.deb"
    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(_tar_control(control)),
    )

    with pytest.raises(PackageError, match="Invalid Debian control file"):
        read_deb_metadata(package)


def test_rejects_control_archive_without_control_file(tmp_path: Path) -> None:
    package = tmp_path / "missing-control.deb"
    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(_tar_without_control()),
    )

    with pytest.raises(PackageError, match="does not contain a regular control file"):
        read_deb_metadata(package)


def test_rejects_oversized_control_file(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = tmp_path / "oversized-control.deb"
    control = b"Package: servcli\nVersion: 1.0.0\nArchitecture: all\n"

    monkeypatch.setattr(deb_module, "MAX_CONTROL_FILE_SIZE", len(control) - 1)
    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(_tar_control(control)),
    )

    with pytest.raises(PackageError, match="control file is too large"):
        read_deb_metadata(package)


def test_rejects_missing_required_control_fields(tmp_path: Path) -> None:
    package = tmp_path / "missing-fields.deb"
    control = b"Package: servcli\nArchitecture: all\n"

    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(_tar_control(control)),
    )

    with pytest.raises(PackageError, match="version"):
        read_deb_metadata(package)


def test_debian_publish_builds_expected_url(tmp_path: Path) -> None:
    package = tmp_path / "servcli.deb"
    _write_deb(
        package,
        "control.tar.gz",
        gzip.compress(_tar_control()),
    )
    client = RecordingClient()

    publish(
        client=client,
        file=package,
        distribution="stable updates",
        component="main+debug",
        dry_run=False,
    )

    assert client.uploaded_url == (
        "https://forge.example.com/api/packages/Software%20Team/debian/pool/"
        "stable%20updates/main%2Bdebug/upload"
    )
    assert client.uploaded_file == package
    assert client.dry_run is False
