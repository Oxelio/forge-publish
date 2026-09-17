from __future__ import annotations

import bz2
import gzip
import io
import lzma
import tarfile
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

import zstandard

from ..client import ForgejoClient
from ..errors import PackageError

AR_MAGIC = b"!<arch>\n"
AR_HEADER_SIZE = 60
AR_HEADER_TRAILER = b"`\n"
MAX_CONTROL_ARCHIVE_COMPRESSED_SIZE = 8 * 1024 * 1024
MAX_CONTROL_ARCHIVE_SIZE = 16 * 1024 * 1024
MAX_CONTROL_FILE_SIZE = 1 * 1024 * 1024


def _is_control_archive(name: str) -> bool:
    return name == "control.tar" or name.startswith("control.tar.")


def _read_ar_header(
    stream: BinaryIO,
    filename: str,
) -> bytes | None:
    header = stream.read(AR_HEADER_SIZE)

    if not header:
        return None

    if len(header) != AR_HEADER_SIZE:
        raise PackageError(f"{filename} contains a truncated ar archive.")

    if header[58:60] != AR_HEADER_TRAILER:
        raise PackageError(f"{filename} contains an invalid ar header.")

    return header


def _parse_ar_header(
    header: bytes,
    filename: str,
) -> tuple[str, int]:
    name = (
        header[0:16]
        .decode(
            "utf-8",
            errors="replace",
        )
        .strip()
        .rstrip("/")
    )

    size_text = (
        header[48:58]
        .decode(
            "ascii",
            errors="replace",
        )
        .strip()
    )

    try:
        size = int(size_text)
    except ValueError as exc:
        raise PackageError(f"Invalid ar member size in {filename}.") from exc

    if size < 0:
        raise PackageError(f"Invalid ar member size in {filename}.")

    return name, size


def _read_ar_member(
    stream: BinaryIO,
    size: int,
    filename: str,
) -> bytes:
    content = stream.read(size)

    if len(content) != size:
        raise PackageError(f"{filename} contains a truncated ar member.")

    return content


def _consume_ar_padding(
    stream: BinaryIO,
    size: int,
    filename: str,
) -> None:
    if size % 2 == 0:
        return

    padding = stream.read(1)

    if len(padding) != 1:
        raise PackageError(f"{filename} contains a truncated ar archive.")


def _read_control_archive_member(
    stream: BinaryIO,
    size: int,
    filename: str,
) -> bytes:
    if size > MAX_CONTROL_ARCHIVE_COMPRESSED_SIZE:
        raise PackageError(f"Debian control archive is too large in {filename}.")

    return _read_ar_member(
        stream,
        size,
        filename,
    )


def _read_control_archive(
    file: Path,
) -> tuple[str, bytes]:
    """Read only the Debian control archive from a .deb ar archive."""
    try:
        with file.open("rb") as stream:
            if stream.read(len(AR_MAGIC)) != AR_MAGIC:
                raise PackageError(f"{file.name} is not a valid Debian package.")

            debian_binary_valid = False
            control_archive: tuple[str, bytes] | None = None

            while True:
                header = _read_ar_header(stream, file.name)

                if header is None:
                    break

                name, size = _parse_ar_header(
                    header,
                    file.name,
                )

                if name == "debian-binary":
                    content = _read_ar_member(
                        stream,
                        size,
                        file.name,
                    )
                    debian_binary_valid = content.strip() == b"2.0"

                elif _is_control_archive(name):
                    content = _read_control_archive_member(
                        stream,
                        size,
                        file.name,
                    )
                    control_archive = (name, content)

                else:
                    stream.seek(size, 1)

                _consume_ar_padding(
                    stream,
                    size,
                    file.name,
                )

                if debian_binary_valid and control_archive is not None:
                    return control_archive

    except OSError as exc:
        raise PackageError(f"Unable to read {file}.") from exc

    if not debian_binary_valid:
        raise PackageError(
            f"{file.name} does not contain a valid debian-binary member."
        )

    raise PackageError(f"{file.name} does not contain a control archive.")


def _read_limited(
    stream: BinaryIO,
    limit: int,
    filename: str,
) -> bytes:
    data = stream.read(limit + 1)

    if len(data) > limit:
        raise PackageError(
            f"Decompressed Debian control archive is too large: {filename}"
        )

    return data


def _decompress_control(data: bytes, filename: str) -> bytes:
    try:
        if filename == "control.tar":
            if len(data) > MAX_CONTROL_ARCHIVE_SIZE:
                raise PackageError(f"Debian control archive is too large: {filename}")

            return data

        source = io.BytesIO(data)

        if filename.endswith(".gz"):
            with gzip.GzipFile(fileobj=source, mode="rb") as stream:
                return _read_limited(
                    stream,
                    MAX_CONTROL_ARCHIVE_SIZE,
                    filename,
                )

        if filename.endswith((".xz", ".lzma")):
            with lzma.LZMAFile(source, mode="rb") as stream:
                return _read_limited(
                    stream,
                    MAX_CONTROL_ARCHIVE_SIZE,
                    filename,
                )

        if filename.endswith(".bz2"):
            with bz2.BZ2File(source, mode="rb") as stream:
                return _read_limited(
                    stream,
                    MAX_CONTROL_ARCHIVE_SIZE,
                    filename,
                )

        if filename.endswith(".zst"):
            with zstandard.ZstdDecompressor().stream_reader(source) as stream:
                return _read_limited(
                    stream,
                    MAX_CONTROL_ARCHIVE_SIZE,
                    filename,
                )

    except PackageError:
        raise
    except (
        OSError,
        EOFError,
        lzma.LZMAError,
        zstandard.ZstdError,
    ) as exc:
        raise PackageError(
            f"Unable to decompress Debian control archive: {filename}"
        ) from exc

    raise PackageError(f"Unsupported control archive format: {filename}")


def _parse_control(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    text = data.decode("utf-8", errors="replace")
    current_key: str | None = None

    for line in text.splitlines():
        if line.startswith((" ", "\t")) and current_key:
            result[current_key] += "\n" + line.strip()
            continue

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip().casefold()
        value = value.strip()

        if key:
            result[key] = value
            current_key = key

    return result


def _validate_path_segment(value: str, field: str) -> None:
    if not value or value != value.strip():
        raise PackageError(
            f"{field} must be non-empty and must not have "
            "leading or trailing whitespace."
        )

    if value in {".", ".."}:
        raise PackageError(
            f"Invalid {field}: {value!r}. Path traversal segments are not allowed."
        )


def read_deb_metadata(file: Path) -> dict[str, str]:
    control_member, compressed_data = _read_control_archive(file)
    control_tar_data = _decompress_control(
        compressed_data,
        control_member,
    )

    try:
        with tarfile.open(
            fileobj=io.BytesIO(control_tar_data),
            mode="r:",
        ) as archive:
            control_file = next(
                (
                    member
                    for member in archive.getmembers()
                    if member.name in ("./control", "control")
                ),
                None,
            )

            if control_file is None or not control_file.isfile():
                raise PackageError(
                    f"{file.name} does not contain a regular control file."
                )

            if control_file.size > MAX_CONTROL_FILE_SIZE:
                raise PackageError(f"Debian control file is too large in {file.name}.")

            extracted = archive.extractfile(control_file)
            if extracted is None:
                raise PackageError(f"Unable to read control file from {file.name}.")

            control_data = extracted.read(MAX_CONTROL_FILE_SIZE + 1)

            if len(control_data) > MAX_CONTROL_FILE_SIZE:
                raise PackageError(f"Debian control file is too large in {file.name}.")
    except tarfile.TarError as exc:
        raise PackageError(f"Invalid control archive in {file.name}.") from exc

    control = _parse_control(control_data)
    required = ("package", "version", "architecture")
    missing = [field for field in required if not control.get(field)]

    if missing:
        raise PackageError("Missing Debian control fields: " + ", ".join(missing))

    return {
        "name": control["package"],
        "version": control["version"],
        "architecture": control["architecture"],
    }


def publish(
    client: ForgejoClient,
    file: Path,
    distribution: str,
    component: str,
    dry_run: bool = False,
) -> None:
    _validate_path_segment(distribution, "distribution")
    _validate_path_segment(component, "component")
    metadata = read_deb_metadata(file)

    print()
    print("Debian package")
    print("--------------")
    print(f"Name         : {metadata['name']}")
    print(f"Version      : {metadata['version']}")
    print(f"Architecture : {metadata['architecture']}")
    print(f"Distribution : {distribution}")
    print(f"Component    : {component}")

    owner = quote(client.config.owner, safe="")
    encoded_distribution = quote(distribution, safe="")
    encoded_component = quote(component, safe="")
    url = (
        f"{client.config.url}"
        f"/api/packages/{owner}"
        f"/debian/pool/{encoded_distribution}"
        f"/{encoded_component}/upload"
    )

    print(f"URL          : {url}")

    client.upload(
        url=url,
        file=file,
        dry_run=dry_run,
    )

    if not dry_run:
        print()
        print("✓ Debian package published successfully.")
