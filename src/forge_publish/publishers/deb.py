from __future__ import annotations

import gzip
import io
import lzma
import tarfile
from pathlib import Path
import zstandard

from ..client import ForgejoClient


def _read_ar_members(file: Path) -> dict[str, bytes]:
    """
    Read the members of a Debian .deb archive.

    A .deb is an ar archive containing files such as:
        debian-binary
        control.tar.*
        data.tar.*

    This implementation avoids requiring dpkg-deb, making the CLI
    usable on Windows as well as Linux.
    """

    data = file.read_bytes()

    if not data.startswith(b"!<arch>\n"):
        raise RuntimeError(
            f"{file.name} is not a valid Debian package."
        )

    offset = 8
    members: dict[str, bytes] = {}

    while offset < len(data):
        if offset + 60 > len(data):
            raise RuntimeError(
                f"{file.name} contains a truncated ar archive."
            )

        header = data[offset:offset + 60]

        name = header[0:16].decode(
            "utf-8",
            errors="replace",
        ).strip()

        size_text = header[48:58].decode(
            "ascii",
            errors="replace",
        ).strip()

        try:
            size = int(size_text)
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid ar member size in {file.name}."
            ) from exc

        content_start = offset + 60
        content_end = content_start + size

        if content_end > len(data):
            raise RuntimeError(
                f"{file.name} contains a truncated ar member."
            )

        members[name.rstrip("/")] = data[
            content_start:content_end
        ]

        offset = content_end

        # ar members are aligned to even offsets.
        if offset % 2:
            offset += 1

    return members


def _decompress_control(data: bytes, filename: str) -> bytes:
    if filename.endswith(".gz"):
        return gzip.decompress(data)

    if filename.endswith(".xz"):
        return lzma.decompress(data)

    if filename.endswith(".zst"):
        return zstandard.ZstdDecompressor().decompress(data)

    if filename.endswith(".bz2"):
        import bz2

        return bz2.decompress(data)

    if filename.endswith(".lzma"):
        return lzma.decompress(data)

    raise RuntimeError(
        f"Unsupported control archive format: {filename}"
    )


def _parse_control(data: bytes) -> dict[str, str]:
    result: dict[str, str] = {}

    text = data.decode(
        "utf-8",
        errors="replace",
    )

    current_key: str | None = None

    for line in text.splitlines():
        # Debian control files support continuation lines.
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
    members = _read_ar_members(file)

    control_member = next(
        (
            name
            for name in members
            if name.startswith("control.tar.")
        ),
        None,
    )

    if control_member is None:
        raise RuntimeError(
            f"{file.name} does not contain a control archive."
        )

    control_tar_data = _decompress_control(
        members[control_member],
        control_member,
    )

    try:
        with tarfile.open(
            fileobj=io.BytesIO(control_tar_data),
            mode="r:",
        ) as archive:

            control_file = None

            for member in archive.getmembers():
                if member.name in (
                    "./control",
                    "control",
                ):
                    control_file = member
                    break

            if control_file is None:
                raise RuntimeError(
                    f"{file.name} does not contain a control file."
                )

            extracted = archive.extractfile(control_file)

            if extracted is None:
                raise RuntimeError(
                    f"Unable to read control file from {file.name}."
                )

            control_data = extracted.read()

    except tarfile.TarError as exc:
        raise RuntimeError(
            f"Invalid control archive in {file.name}."
        ) from exc

    control = _parse_control(control_data)

    required = (
        "Package",
        "Version",
        "Architecture",
    )

    missing = [
        field
        for field in required
        if not control.get(field)
    ]

    if missing:
        raise RuntimeError(
            f"Missing Debian control fields: "
            f"{', '.join(missing)}"
        )

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

    url = (
        f"{client.config.url}"
        f"/api/packages/{client.config.owner}"
        f"/debian/pool/{distribution}"
        f"/{component}/upload"
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