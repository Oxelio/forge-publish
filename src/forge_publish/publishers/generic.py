from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import quote

from ..client import ForgejoClient
from ..errors import PackageError

GENERIC_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._+-]+$")


def _validate_name(value: str, field: str) -> None:
    if value in {".", ".."}:
        raise PackageError(
            f"Invalid {field}: {value!r}. Path traversal segments are not allowed."
        )

    if not GENERIC_NAME_PATTERN.fullmatch(value):
        raise PackageError(
            f"Invalid {field}: {value!r}. Allowed characters are "
            "A-Z, a-z, 0-9, '.', '-', '+', and '_'."
        )


def _validate_version(version: str) -> None:
    if not version or version != version.strip():
        raise PackageError(
            "Package version must be non-empty and must not have "
            "leading or trailing whitespace."
        )

    if version in {".", ".."}:
        raise PackageError(
            f"Invalid package version: {version!r}. "
            "Path traversal segments are not allowed."
        )


def publish(
    client: ForgejoClient,
    file: Path,
    package_name: str,
    version: str,
    filename: str | None = None,
    dry_run: bool = False,
) -> None:
    if filename is None:
        filename = file.name

    _validate_name(package_name, "package name")
    _validate_version(version)
    _validate_name(filename, "filename")

    owner = quote(client.config.owner, safe="")
    encoded_package = quote(package_name, safe="")
    encoded_version = quote(version, safe="")
    encoded_filename = quote(filename, safe="")
    url = (
        f"{client.config.url}"
        f"/api/packages/{owner}"
        f"/generic/{encoded_package}"
        f"/{encoded_version}"
        f"/{encoded_filename}"
    )

    print()
    print("Generic package")
    print("----------------")
    print(f"Package : {package_name}")
    print(f"Version : {version}")
    print(f"File    : {filename}")
    print(f"URL     : {url}")

    client.upload(
        url=url,
        file=file,
        dry_run=dry_run,
    )

    if not dry_run:
        print()
        print("✓ Generic package published successfully.")
