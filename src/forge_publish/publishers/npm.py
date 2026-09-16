from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ..client import ForgejoClient


def read_package_json(directory: Path) -> dict:
    package_json = directory / "package.json"

    if not package_json.exists():
        raise RuntimeError(
            f"package.json not found in {directory}"
        )

    with package_json.open() as f:
        return json.load(f)


def publish(
    client: ForgejoClient,
    directory: Path,
    dry_run: bool = False,
) -> None:

    package = read_package_json(directory)

    name = package.get("name")
    version = package.get("version")

    if not name:
        raise RuntimeError(
            "package.json does not contain a 'name'."
        )

    if not version:
        raise RuntimeError(
            "package.json does not contain a 'version'."
        )

    registry = (
        f"{client.config.url}"
        f"/api/packages/{client.config.owner}/npm/"
    )

    print()
    print("NPM package")
    print("-----------")
    print(f"Name     : {name}")
    print(f"Version  : {version}")
    print(f"Registry : {registry}")

    if dry_run:
        print()
        print("DRY RUN")
        print("-------")
        print(
            f"npm publish --registry={registry}"
        )
        return

    try:
        subprocess.run(
            [
                "npm",
                "publish",
                f"--registry={registry}",
            ],
            cwd=directory,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "npm is not installed or not available in PATH."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"npm publish failed with exit code {exc.returncode}"
        ) from exc

    print()
    print("✓ NPM package published successfully.")