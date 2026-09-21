from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote, urlsplit

from ..client import ForgejoClient
from ..config import TOKEN_ENV_VAR
from ..errors import PackageError


def read_package_json(directory: Path) -> dict[str, object]:
    package_json = directory / "package.json"

    if not package_json.exists():
        raise PackageError(f"package.json not found in {directory}")

    try:
        with package_json.open(encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError as exc:
        raise PackageError(f"Invalid JSON in {package_json}.") from exc
    except OSError as exc:
        raise PackageError(f"Unable to read {package_json}.") from exc

    if not isinstance(data, dict):
        raise PackageError("package.json must contain a JSON object.")

    return data


def _npm_auth_key(registry: str) -> str:
    parsed = urlsplit(registry)
    return f"//{parsed.netloc}{parsed.path}:_authToken"


def _write_temporary_npmrc(
    directory: Path,
    registry: str,
    token: str,
) -> Path:
    npmrc = directory / ".npmrc"

    npmrc.write_text(
        f"registry={registry}\n{_npm_auth_key(registry)}={token}\n",
        encoding="utf-8",
    )

    try:
        os.chmod(npmrc, 0o600)
    except OSError:
        # Permissions are best-effort and vary across platforms.
        pass

    return npmrc


def publish(
    client: ForgejoClient,
    directory: Path,
    *,
    dry_run: bool,
) -> None:
    package = read_package_json(directory)

    name = package.get("name")
    version = package.get("version")

    if not isinstance(name, str) or not name.strip():
        raise PackageError("package.json does not contain a valid 'name'.")

    if not isinstance(version, str) or not version.strip():
        raise PackageError("package.json does not contain a valid 'version'.")

    owner = quote(client.config.owner, safe="")
    registry = f"{client.config.url}/api/packages/{owner}/npm/"

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
        print("npm pack --pack-destination=<temporary directory>")
        print(
            f"npm publish <packed .tgz> --registry={registry} "
            "--userconfig=<temporary .npmrc> --ignore-scripts"
        )
        return

    token = client.config.token

    if not token:
        raise PackageError("No Forgejo token configured.")

    npm_executable = shutil.which("npm")

    if npm_executable is None:
        raise PackageError("npm is not installed or not available in PATH.")

    environment = os.environ.copy()
    environment.pop(TOKEN_ENV_VAR, None)

    try:
        with tempfile.TemporaryDirectory(
            prefix="forge-publish-"
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)

            try:
                subprocess.run(
                    [
                        npm_executable,
                        "pack",
                        f"--pack-destination={temporary_path}",
                    ],
                    cwd=directory,
                    check=True,
                    env=environment,
                )
            except subprocess.CalledProcessError as exc:
                raise PackageError(
                    f"npm pack failed with exit code {exc.returncode}"
                ) from exc

            archives = list(temporary_path.glob("*.tgz"))
            if len(archives) != 1:
                raise PackageError(
                    "npm pack did not produce exactly one package archive."
                )

            npmrc = _write_temporary_npmrc(
                temporary_path,
                registry,
                token,
            )

            try:
                subprocess.run(
                    [
                        npm_executable,
                        "publish",
                        str(archives[0]),
                        f"--registry={registry}",
                        f"--userconfig={npmrc}",
                        "--ignore-scripts",
                    ],
                    cwd=directory,
                    check=True,
                    env=environment,
                )
            except subprocess.CalledProcessError as exc:
                raise PackageError(
                    f"npm publish failed with exit code {exc.returncode}"
                ) from exc

    except OSError as exc:
        raise PackageError(
            "Unable to create or use the temporary npm configuration."
        ) from exc

    print()
    print("✓ NPM package published successfully.")
