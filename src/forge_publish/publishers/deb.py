from __future__ import annotations

import bz2
import gzip
import io
import lzma
import tarfile
from pathlib import Path
from urllib.parse import quote

import zstandard

from ..client import ForgejoClient
from ..errors import PackageError

AR_MAGIC = b"!<arch>\n"
AR_HEADER_SIZE = 60
AR_HEADER_TRAILER = b"`\n"


def _read_control_archive(file: Path) -> tuple[str, bytes]:
    """Read only the Debian control archive from a .deb ar archive."""
    try:
        with file.open("rb") as stream:
            if stream.read(len(AR_MAGIC)) != AR_MAGIC:
                raise PackageError(f"{file.name} is not a valid Debian package.")

            debian_binary_valid = False
            control_archive: tuple[str, bytes] | None = None

            while True:
                header = stream.read(AR_HEADER_SIZE)
                if not header:
                    break

                if len(header) != AR_HEADER_SIZE:
                    raise PackageError(f"{file.name} contains a truncated ar archive.")

                if header[58:60] != AR_HEADER_TRAILER:
                    raise PackageError(f"{file.name} contains an invalid ar header.")

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
                    raise PackageError(
                        f"Invalid ar member size in {file.name}."
                    ) from exc

                if size < 0:
                    raise PackageError(f"Invalid ar member size in {file.name}.")

                if name == "debian-binary":
                    content = stream.read(size)
                    if len(content) != size:
                        raise PackageError(
                            f"{file.name} contains a truncated ar member."
                        )
                    debian_binary_valid = content.strip() == b"2.0"
                elif name == "control.tar" or name.startswith("control.tar."):
                    content = stream.read(size)
                    if len(content) != size:
                        raise PackageError(
                            f"{file.name} contains a truncated ar member."
                        )
                    control_archive = (name, content)
                else:
                    stream.seek(size, 1)

                if size % 2:
                    padding = stream.read(1)
                    if len(padding) != 1:
                        raise PackageError(
                            f"{file.name} contains a truncated ar archive."
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


def _decompress_control(data: bytes, filename: str) -> bytes:
    try:
        if filename == "control.tar":
            return data
        if filename.endswith(".gz"):
            return gzip.decompress(data)
        if filename.endswith(".xz"):
            return lzma.decompress(data)
        if filename.endswith(".zst"):
            with zstandard.ZstdDecompressor().stream_reader(io.BytesIO(data)) as reader:
                return reader.read()
        if filename.endswith(".bz2"):
            return bz2.decompress(data)
        if filename.endswith(".lzma"):
            return lzma.decompress(data)
    except (OSError, lzma.LZMAError, zstandard.ZstdError) as exc:
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
        key = key.strip()
        value = value.strip()

        if key:
            result[key] = value
            current_key = key

    return result


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

            extracted = archive.extractfile(control_file)
            if extracted is None:
                raise PackageError(f"Unable to read control file from {file.name}.")

            control_data = extracted.read()
    except tarfile.TarError as exc:
        raise PackageError(f"Invalid control archive in {file.name}.") from exc

    control = _parse_control(control_data)
    required = ("Package", "Version", "Architecture")
    missing = [field for field in required if not control.get(field)]

    if missing:
        raise PackageError("Missing Debian control fields: " + ", ".join(missing))

    return {
        "name": control["Package"],
        "version": control["Version"],
        "architecture": control["Architecture"],
    }


def publish(
    client: ForgejoClient,
    file: Path,
    distribution: str,
    component: str,
    dry_run: bool = False,
) -> None:
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
