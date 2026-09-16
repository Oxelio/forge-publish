from __future__ import annotations

from pathlib import Path

from ..client import ForgejoClient


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

    url = (
        f"{client.config.url}"
        f"/api/packages/{client.config.owner}"
        f"/generic/{package_name}"
        f"/{version}"
        f"/{filename}"
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