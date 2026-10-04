"""Small, reproducible in-memory fuzz corpus; see docs/development.md."""

import bz2
import gzip
import io
import lzma
import random
import string
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest
import zstandard
from test_deb import (
    _ar_member,
    _invalid_deflate_archive,
    _malformed_tar_extension,
    _oversized_decoder_archive,
    _tar_control,
)

from forge_publish.errors import PackageError
from forge_publish.publishers import deb

SEED = 47
INPUT_LIMIT = 32 * 1024
FORMATS = ("tar", "gz", "bz2", "xz", "lzma", "zst")


@pytest.fixture(autouse=True)
def bounded_parser(monkeypatch):
    # Small real limits exercise production guards without large allocations.
    monkeypatch.setattr(deb, "MAX_CONTROL_ARCHIVE_COMPRESSED_SIZE", INPUT_LIMIT)
    monkeypatch.setattr(deb, "MAX_CONTROL_ARCHIVE_SIZE", INPUT_LIMIT)
    monkeypatch.setattr(deb, "MAX_CONTROL_FILE_SIZE", 4096)
    monkeypatch.setattr(deb, "MAX_LZMA_MEMORY", 1024 * 1024)
    monkeypatch.setattr(deb, "MAX_ZSTD_WINDOW_SIZE", 1024 * 1024)

    def forbidden_extraction(*args, **kwargs):
        raise AssertionError("The metadata parser must not extract to disk")

    monkeypatch.setattr(tarfile.TarFile, "extract", forbidden_extraction)
    monkeypatch.setattr(tarfile.TarFile, "extractall", forbidden_extraction)


def _compress(data: bytes, format: str) -> bytes:
    if format == "tar":
        return data
    if format == "gz":
        return gzip.compress(data, mtime=0)
    if format == "bz2":
        return bz2.compress(data)
    if format in ("xz", "lzma"):
        return lzma.compress(
            data,
            format=lzma.FORMAT_XZ if format == "xz" else lzma.FORMAT_ALONE,
            filters=[
                {
                    "id": lzma.FILTER_LZMA2 if format == "xz" else lzma.FILTER_LZMA1,
                    "dict_size": 4096,
                }
            ],
        )
    assert format == "zst"
    return zstandard.ZstdCompressor().compress(data)


def _archive(control: bytes, format: str) -> bytes:
    name = "control.tar" if format == "tar" else f"control.tar.{format}"
    return (
        deb.AR_MAGIC
        + _ar_member("debian-binary", b"2.0\n")
        + _ar_member(name, _compress(control, format))
    )


def _read(data: bytes, case: str) -> dict[str, str]:
    assert len(data) <= INPUT_LIMIT, case

    class BoundedInput(io.BytesIO):
        def read(self, size: int = -1) -> bytes:
            assert 0 <= size <= INPUT_LIMIT, (case, size)
            return super().read(size)

    # Only the input stream exists: no package or extracted files are written.
    package = Mock(spec=Path)
    package.name = "fuzz.deb"
    package.open.return_value = BoundedInput(data)
    try:
        result = deb.read_deb_metadata(package)
    except Exception as exc:
        exc.add_note(f"Debian fuzz seed={SEED}, case={case}")
        raise
    package.open.assert_called_once_with("rb")
    assert set(result) == {"name", "version", "architecture"}, case
    assert all(isinstance(value, str) and value for value in result.values()), case
    return result


def _valid_or_package_error(data: bytes, case: str) -> None:
    # Arbitrary input can still be valid; unexpected exceptions must escape.
    try:
        _read(data, case)
    except PackageError:
        pass


def _mutate(data: bytes, rng: random.Random) -> bytes:
    mutated = bytearray(data)
    for _ in range(rng.randint(1, 8)):
        offset = rng.randrange(len(mutated))
        mutated[offset] ^= rng.randint(1, 255)
    return bytes(mutated)


def test_arbitrary_bytes_have_only_documented_outcomes():
    rng = random.Random(SEED)
    for index in range(256):
        data = rng.randbytes(rng.randrange(2049))
        _valid_or_package_error(data, f"raw-{index}")
        # Preserve ar magic so arbitrary bytes also reach header parsing.
        _valid_or_package_error(deb.AR_MAGIC + data, f"ar-{index}")


@pytest.mark.parametrize("format", FORMATS)
def test_seeded_mutations_and_truncations(format):
    rng = random.Random(SEED)
    seeds = [_tar_control()] + [
        _malformed_tar_extension(kind)
        for kind in (
            "sparse-empty",
            "sparse-short",
            "pax",
            "gnu-longname",
            "gnu-longlink",
        )
    ]
    for seed_index, control in enumerate(seeds):
        archive = _archive(control, format)
        _valid_or_package_error(archive, f"{format}-{seed_index}-original")
        # Exhaust ar headers and sample arbitrary deeper offsets/end boundaries.
        offsets = set(range(min(133, len(archive)))) | {
            0,
            len(archive) - 1,
            len(archive),
        }
        offsets.update(rng.randrange(len(archive) + 1) for _ in range(32))
        for offset in sorted(offsets):
            _valid_or_package_error(
                archive[:offset], f"{format}-{seed_index}-truncate-{offset}"
            )
        for index in range(24):
            _valid_or_package_error(
                _mutate(archive, rng), f"{format}-{seed_index}-ar-mutation-{index}"
            )
            # Rebuild ar/compression around mutated tar to reach the tar parser.
            _valid_or_package_error(
                _archive(_mutate(control, rng), format),
                f"{format}-{seed_index}-tar-mutation-{index}",
            )


@pytest.mark.parametrize("format", FORMATS)
def test_generated_control_metadata_round_trips(format):
    rng = random.Random(SEED)
    for index in range(32):
        name = "pkg-" + "".join(rng.choices(string.ascii_lowercase, k=16))
        version = f"{rng.randrange(100)}.{rng.randrange(100)}-{rng.randrange(100)}"
        architecture = rng.choice(("all", "amd64", "arm64", "i386"))
        fields = [
            f"Package: {name}",
            f"VERSION:\t{version} ",
            f"architecture: {architecture}",
            "Description: generated\n continuation",
        ]
        rng.shuffle(fields)
        newline = rng.choice(("\n", "\r\n"))
        control = (newline.join(fields) + newline).encode()
        assert _read(_archive(_tar_control(control), format), f"roundtrip-{index}") == {
            "name": name,
            "version": version,
            "architecture": architecture,
        }
        for mutation in range(16):
            _valid_or_package_error(
                _archive(_tar_control(_mutate(control, rng)), format),
                f"{format}-control-{index}-{mutation}",
            )


@pytest.mark.parametrize("member", ("debian-binary", "control.tar.gz"))
def test_declared_ar_sizes_are_rejected_before_payload_reads(member):
    rng = random.Random(SEED)
    limit = (
        deb.MAX_DEBIAN_BINARY_SIZE
        if member == "debian-binary"
        else deb.MAX_CONTROL_ARCHIVE_COMPRESSED_SIZE
    )
    for size in [limit + 1, 9999999999] + [
        rng.randrange(limit + 1, 9999999999) for _ in range(64)
    ]:
        header = bytearray(_ar_member(member, b"")[:60])
        header[48:58] = f"{size:<10}".encode("ascii")
        # No declared payload is allocated. Even a small oversized read fails.
        stream = Mock(wraps=io.BytesIO(deb.AR_MAGIC + bytes(header)))
        package = Mock(spec=Path)
        package.name = "size.deb"
        package.open.return_value.__enter__ = Mock(return_value=stream)
        package.open.return_value.__exit__ = Mock(return_value=False)
        with pytest.raises(PackageError, match="too large"):
            deb.read_deb_metadata(package)
        assert [call.args[0] for call in stream.read.call_args_list] == [8, 60]


@pytest.mark.parametrize("format", FORMATS)
def test_generated_decompression_and_control_size_limits(monkeypatch, format):
    rng = random.Random(SEED)
    for index in range(12):
        control = (
            b"Package: generated\nVersion: 1.0\nArchitecture: all\nDescription: "
            + b"a" * rng.randrange(1, 256)
            + b"\n"
        )
        tar = _tar_control(control)
        archive = _archive(tar, format)
        monkeypatch.setattr(deb, "MAX_CONTROL_FILE_SIZE", len(control))
        monkeypatch.setattr(deb, "MAX_CONTROL_ARCHIVE_SIZE", len(tar))
        assert _read(archive, f"limit-accepted-{index}")["name"] == "generated"
        monkeypatch.setattr(deb, "MAX_CONTROL_FILE_SIZE", len(control) - 1)
        with pytest.raises(PackageError, match="control file is too large"):
            _read(archive, f"control-limit-{index}")
        monkeypatch.setattr(deb, "MAX_CONTROL_FILE_SIZE", len(control))
        monkeypatch.setattr(deb, "MAX_CONTROL_ARCHIVE_SIZE", len(tar) - 1)
        with pytest.raises(PackageError, match="too large"):
            _read(archive, f"decompression-limit-{index}")


@pytest.mark.parametrize("format", ("gz", "xz", "lzma", "zst"))
def test_decoder_memory_regression_seeds(format):
    name = f"control.tar.{format}"
    compressed = (
        _invalid_deflate_archive()
        if format == "gz"
        else _oversized_decoder_archive(name)
    )
    archive = (
        deb.AR_MAGIC
        + _ar_member("debian-binary", b"2.0\n")
        + _ar_member(name, compressed)
    )
    with pytest.raises(PackageError, match="Unable to decompress"):
        _read(archive, f"{format}-decoder-memory")
