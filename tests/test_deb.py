import bz2
import gzip
import io
import lzma
import tarfile
import zlib
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest
import zstandard
from click.testing import CliRunner

from forge_publish import cli
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


@pytest.mark.parametrize("status_code", [301, 302, 303, 307, 308])
def test_debian_redirect_is_reported_without_success(
    tmp_path: Path, monkeypatch, redirect_session, status_code: int
) -> None:
    package = tmp_path / "package.deb"
    _write_deb(package, "control.tar", _tar_control())
    config = Config(
        url="https://forge.example.com",
        owner="Software",
        username="user",
        token="secret",
    )
    monkeypatch.setattr(cli, "load_config", lambda *, require_token: config)
    session, adapter = redirect_session(status_code)
    monkeypatch.setattr("forge_publish.client.requests.Session", lambda: session)

    result = CliRunner().invoke(
        main,
        ["deb", str(package), "--distribution", "stable", "--component", "main"],
    )

    assert result.exit_code == 1
    assert f"Error: HTTP {status_code}:" in result.output
    assert "canonical Forgejo URL" in result.output
    assert "published successfully" not in result.output
    assert "Traceback" not in result.output
    assert len(adapter.requests) == 1
    assert adapter.requests[0][0] == "PUT"


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


@pytest.mark.parametrize("format", [lzma.FORMAT_XZ, lzma.FORMAT_ALONE])
def test_lzma_decoder_memory_boundary(monkeypatch, format: int) -> None:
    # Exercise the real decoder near a small test bound, not a large allocation.
    monkeypatch.setattr(deb_module, "MAX_LZMA_MEMORY", 1024 * 1024)
    filter_id = lzma.FILTER_LZMA2 if format == lzma.FORMAT_XZ else lzma.FILTER_LZMA1
    control = _tar_control()
    filename = "control.tar.xz" if format == lzma.FORMAT_XZ else "control.tar.lzma"
    accepted = lzma.compress(
        control, format=format, filters=[{"id": filter_id, "dict_size": 512 * 1024}]
    )
    rejected = lzma.compress(
        control, format=format, filters=[{"id": filter_id, "dict_size": 1024 * 1024}]
    )

    assert deb_module._decompress_control(accepted, filename) == control
    with pytest.raises(PackageError, match="Unable to decompress") as exc_info:
        deb_module._decompress_control(rejected, filename)
    assert isinstance(exc_info.value.__cause__, lzma.LZMAError)


def _oversized_decoder_archive(filename: str) -> bytes:
    # Mutate only decoder parameters in a tiny valid frame. No large compressor
    # dictionary, source payload or memory-exhaustion workload is constructed.
    control = _tar_control()
    if filename == "control.tar.zst":
        data = bytearray(
            zstandard.ZstdCompressor(write_content_size=False).compress(control)
        )
        data[5] = 136  # Non-single-segment frame: 128 MiB window.
        assert zstandard.get_frame_parameters(data).window_size == 128 * 1024 * 1024
    elif filename == "control.tar.xz":
        data = bytearray(lzma.compress(control))
        data[16] = 32  # LZMA2 filter property: 256 MiB dictionary.
        data[20:24] = zlib.crc32(data[12:20]).to_bytes(4, "little")
    else:
        data = bytearray(lzma.compress(control, format=lzma.FORMAT_ALONE))
        data[1:5] = (256 * 1024 * 1024).to_bytes(4, "little")
    return bytes(data)


@pytest.mark.parametrize(
    "filename", ["control.tar.xz", "control.tar.lzma", "control.tar.zst"]
)
def test_rejects_hostile_decoder_parameters_before_upload(
    tmp_path: Path, filename: str
) -> None:
    package = tmp_path / "hostile.deb"
    _write_deb(package, filename, _oversized_decoder_archive(filename))

    with pytest.raises(PackageError, match="Unable to decompress") as exc_info:
        publish(
            client=FakeClient(),
            file=package,
            distribution="stable",
            component="main",
            dry_run=False,
        )
    assert isinstance(exc_info.value.__cause__, (lzma.LZMAError, zstandard.ZstdError))


def test_zstd_window_boundary_uses_bytes(monkeypatch) -> None:
    monkeypatch.setattr(deb_module, "MAX_ZSTD_WINDOW_SIZE", 16 * 1024)
    control = _tar_control()
    frame = bytearray(
        zstandard.ZstdCompressor(write_content_size=False).compress(control)
    )
    frame[5] = 32  # 16 KiB window, exactly the configured bound.
    assert zstandard.get_frame_parameters(frame).window_size == 16 * 1024
    assert deb_module._decompress_control(bytes(frame), "control.tar.zst") == control

    frame[5] = 33  # 18 KiB window: immediately above the bound.
    assert zstandard.get_frame_parameters(frame).window_size == 18 * 1024
    with pytest.raises(PackageError, match="Unable to decompress") as exc_info:
        deb_module._decompress_control(bytes(frame), "control.tar.zst")
    assert isinstance(exc_info.value.__cause__, zstandard.ZstdError)


@pytest.mark.parametrize(
    ("format", "padding"),
    [
        (lzma.FORMAT_XZ, b""),
        (lzma.FORMAT_XZ, b"\x00" * 4),
        (lzma.FORMAT_XZ, b"\x00" * 8),
        (lzma.FORMAT_ALONE, b""),
    ],
)
def test_lzma_concatenated_streams_keep_output_bound(
    monkeypatch, format: int, padding: bytes
) -> None:
    control = _tar_control()
    split = len(control) // 2
    data = (
        lzma.compress(control[:split], format=format)
        + padding
        + lzma.compress(control[split:], format=format)
        + padding
    )
    filename = "control.tar.xz" if format == lzma.FORMAT_XZ else "control.tar.lzma"
    monkeypatch.setattr(deb_module, "MAX_CONTROL_ARCHIVE_SIZE", len(control))
    assert deb_module._decompress_control(data, filename) == control

    monkeypatch.setattr(deb_module, "MAX_CONTROL_ARCHIVE_SIZE", len(control) - 1)
    with pytest.raises(PackageError, match="too large"):
        deb_module._decompress_control(data, filename)


@pytest.mark.parametrize(
    "filename", ["control.tar.xz", "control.tar.lzma", "control.tar.zst"]
)
def test_decoder_error_is_reported_by_cli_dry_run(
    tmp_path: Path, monkeypatch, filename: str
) -> None:
    package = tmp_path / "hostile.deb"
    _write_deb(package, filename, _oversized_decoder_archive(filename))
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
    assert (
        result.output
        == f"Error: Unable to decompress Debian control archive: {filename}\n"
    )


@pytest.mark.parametrize("format", [lzma.FORMAT_XZ, lzma.FORMAT_ALONE])
@pytest.mark.parametrize("suffix", [b"", b"\x00", b"garbage"])
def test_lzma_truncation_and_invalid_trailing_data(format: int, suffix: bytes) -> None:
    data = lzma.compress(_tar_control(), format=format)
    filename = "control.tar.xz" if format == lzma.FORMAT_XZ else "control.tar.lzma"
    data = data[:-1] if not suffix else data + suffix
    with pytest.raises(PackageError, match="Unable to decompress"):
        deb_module._decompress_control(data, filename)


@pytest.mark.parametrize("filename", ["control.tar.xz", "control.tar.lzma"])
def test_lzma_rejects_empty_compressed_stream(filename: str) -> None:
    with pytest.raises(PackageError, match="Unable to decompress") as exc_info:
        deb_module._decompress_control(b"", filename)
    assert isinstance(exc_info.value.__cause__, EOFError)


@pytest.mark.parametrize("format", [lzma.FORMAT_XZ, lzma.FORMAT_ALONE])
def test_lzma_memory_limit_applies_to_later_streams(monkeypatch, format: int) -> None:
    monkeypatch.setattr(deb_module, "MAX_LZMA_MEMORY", 1024 * 1024)
    filter_id = lzma.FILTER_LZMA2 if format == lzma.FORMAT_XZ else lzma.FILTER_LZMA1
    first = lzma.compress(
        b"first", format=format, filters=[{"id": filter_id, "dict_size": 512 * 1024}]
    )
    second = lzma.compress(
        b"second", format=format, filters=[{"id": filter_id, "dict_size": 1024 * 1024}]
    )
    filename = "control.tar.xz" if format == lzma.FORMAT_XZ else "control.tar.lzma"
    with pytest.raises(PackageError, match="Unable to decompress") as exc_info:
        deb_module._decompress_control(first + second, filename)
    assert isinstance(exc_info.value.__cause__, lzma.LZMAError)


@pytest.mark.parametrize(
    ("filename", "compress"),
    [
        ("control.tar.xz", lzma.compress),
        (
            "control.tar.lzma",
            lambda data: lzma.compress(data, format=lzma.FORMAT_ALONE),
        ),
        ("control.tar.zst", lambda data: zstandard.ZstdCompressor().compress(data)),
    ],
)
def test_decoder_output_limit_boundary(monkeypatch, filename: str, compress) -> None:
    data = b"x" * 1024
    compressed = compress(data)
    monkeypatch.setattr(deb_module, "MAX_CONTROL_ARCHIVE_SIZE", len(data))
    assert deb_module._decompress_control(compressed, filename) == data
    monkeypatch.setattr(deb_module, "MAX_CONTROL_ARCHIVE_SIZE", len(data) - 1)
    with pytest.raises(PackageError, match="too large"):
        deb_module._decompress_control(compressed, filename)


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


def _malformed_tar_extension(kind: str) -> bytes:
    info = tarfile.TarInfo("extension")
    if kind.startswith("sparse"):
        info.type = tarfile.GNUTYPE_SPARSE
        header = bytearray(info.tobuf(format=tarfile.GNU_FORMAT))
        header[482] = 1  # A following GNU sparse extension block is required.
        header[148:156] = b"        "
        header[148:156] = f"{sum(header):06o}\0 ".encode("ascii")
        # Neither missing nor short blocks provide the flag at offset 504.
        return bytes(header) + (b"\0" * 24 if kind == "sparse-short" else b"")

    info.type = {
        "pax": tarfile.XHDTYPE,
        "gnu-longname": tarfile.GNUTYPE_LONGNAME,
        "gnu-longlink": tarfile.GNUTYPE_LONGLINK,
    }[kind]
    info.size = 2**80
    # Encode a declared huge size in the header only. Older tarfile versions
    # overflow on the read size; newer bounded readers see immediate EOF.
    return info.tobuf(format=tarfile.GNU_FORMAT)


@pytest.mark.parametrize(
    "kind", ["sparse-empty", "sparse-short", "pax", "gnu-longname", "gnu-longlink"]
)
@pytest.mark.parametrize("after_control", [False, True])
def test_rejects_malformed_tar_extensions_before_upload(
    tmp_path: Path, kind: str, after_control: bool
) -> None:
    package = tmp_path / "malformed.deb"
    control_tar = _malformed_tar_extension(kind)
    if after_control:
        # A valid first member must not hide malformed metadata discovered
        # while getmembers() traverses the remaining archive.
        control_tar = _tar_control()[:1024] + control_tar
    _write_deb(package, "control.tar", control_tar)

    with pytest.raises(
        PackageError, match=r"Invalid control archive in malformed\.deb\."
    ) as exc_info:
        publish(
            client=FakeClient(),
            file=package,
            distribution="stable",
            component="main",
            dry_run=False,
        )

    # The precise parser error depends on the Python patch release.
    expected = (
        (IndexError, tarfile.TarError)
        if kind.startswith("sparse")
        else (
            OverflowError,
            tarfile.TarError,
        )
    )
    assert isinstance(exc_info.value.__cause__, expected)


@pytest.mark.parametrize(
    "kind", ["sparse-empty", "sparse-short", "pax", "gnu-longname", "gnu-longlink"]
)
def test_tar_extension_error_is_reported_by_cli_dry_run(
    tmp_path: Path, monkeypatch, kind: str
) -> None:
    package = tmp_path / "malformed.deb"
    _write_deb(package, "control.tar", _malformed_tar_extension(kind))
    monkeypatch.setattr(
        config_module,
        "_read_config_data",
        lambda: {
            "url": "https://forge.example.com",
            "owner": "Software",
            "username": "user",
        },
    )
    token_lookup = Mock(side_effect=AssertionError("unexpected token lookup"))
    token_prompt = Mock(side_effect=AssertionError("unexpected token prompt"))
    upload = Mock(side_effect=AssertionError("unexpected upload"))
    request = Mock(side_effect=AssertionError("unexpected HTTP request"))
    monkeypatch.setattr(config_module, "_get_keyring_token", token_lookup)
    monkeypatch.setattr(config_module, "_prompt_token", token_prompt)
    monkeypatch.setattr(deb_module.ForgejoClient, "upload", upload)
    monkeypatch.setattr("requests.sessions.Session.request", request)

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
    assert result.output == "Error: Invalid control archive in malformed.deb.\n"
    assert isinstance(result.exception, SystemExit)
    token_lookup.assert_not_called()
    token_prompt.assert_not_called()
    upload.assert_not_called()
    request.assert_not_called()


@pytest.mark.parametrize("format", [tarfile.PAX_FORMAT, tarfile.GNU_FORMAT])
def test_read_deb_metadata_with_valid_tar_extensions(
    tmp_path: Path, format: int
) -> None:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=format) as archive:
        # A long metadata member exercises PAX/GNU extension handling before
        # the regular control file, without changing Debian metadata.
        archive.addfile(tarfile.TarInfo("metadata/" + "x" * 128))
        control = b"Package: servcli\nVersion: 1.9.3-0\nArchitecture: i386\n"
        info = tarfile.TarInfo("control")
        info.size = len(control)
        archive.addfile(info, io.BytesIO(control))
    package = tmp_path / "valid.deb"
    _write_deb(package, "control.tar", output.getvalue())

    assert read_deb_metadata(package) == {
        "name": "servcli",
        "version": "1.9.3-0",
        "architecture": "i386",
    }


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
