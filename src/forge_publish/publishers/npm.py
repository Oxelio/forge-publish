from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote, urlsplit

from ..client import ForgejoClient
from ..config import TOKEN_ENV_VAR
from ..errors import PackageError

MIN_NPM_VERSION = (10, 5, 2)
MIN_NPM_VERSION_TEXT = ".".join(str(part) for part in MIN_NPM_VERSION)
NPM_VERSION_PATTERN = re.compile(
    r"^(\d+)\.(\d+)\.(\d+)(?P<prerelease>-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
NPM_TOKEN_ENV_VARS = {
    TOKEN_ENV_VAR.casefold(),
    "npm_token",
    "node_auth_token",
}


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
        (f"registry={registry}\nstrict-ssl=true\n{_npm_auth_key(registry)}={token}\n"),
        encoding="utf-8",
    )

    try:
        os.chmod(npmrc, 0o600)
    except OSError:
        # Permissions are best-effort and vary across platforms.
        pass

    return npmrc


def _sanitize_npm_environment(
    environment: Mapping[str, str],
) -> dict[str, str]:
    sanitized: dict[str, str] = {}

    for key, value in environment.items():
        normalized_key = key.casefold()

        if normalized_key in NPM_TOKEN_ENV_VARS:
            continue

        if normalized_key.startswith("npm_config_"):
            continue

        sanitized[key] = value

    return sanitized


def _get_npm_version(
    npm_executable: str,
    *,
    environment: dict[str, str],
) -> str:
    try:
        result = subprocess.run(
            [npm_executable, "--version"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        )
    except subprocess.CalledProcessError as exc:
        raise PackageError(
            f"npm --version failed with exit code {exc.returncode}"
        ) from exc
    except OSError as exc:
        raise PackageError(f"Unable to execute npm --version: {exc}") from exc

    return result.stdout.strip()


def _require_supported_npm(version: str) -> None:
    match = NPM_VERSION_PATTERN.fullmatch(version)

    if match is None:
        raise PackageError(f"Unable to determine npm version from {version!r}.")

    parsed_version = tuple(int(part) for part in match.groups()[:3])
    is_prerelease = match.group("prerelease") is not None

    if parsed_version < MIN_NPM_VERSION or (
        parsed_version == MIN_NPM_VERSION and is_prerelease
    ):
        raise PackageError(
            f"npm {MIN_NPM_VERSION_TEXT} or newer is required; found {version}."
        )


def _run_npm(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    operation: str,
) -> None:
    try:
        subprocess.run(
            command,
            cwd=cwd,
            check=True,
            env=environment,
        )
    except subprocess.CalledProcessError as exc:
        raise PackageError(
            f"npm {operation} failed with exit code {exc.returncode}"
        ) from exc
    except OSError as exc:
        raise PackageError(f"Unable to execute npm {operation}: {exc}") from exc


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
            "--userconfig=<temporary .npmrc> --strict-ssl=true --ignore-scripts"
        )
        return

    token = client.config.token

    if not token:
        raise PackageError("No Forgejo token configured.")

    npm_executable = shutil.which("npm")

    if npm_executable is None:
        raise PackageError("npm is not installed or not available in PATH.")

    environment = _sanitize_npm_environment(os.environ)
    npm_version = _get_npm_version(
        npm_executable,
        environment=environment,
    )
    _require_supported_npm(npm_version)

    try:
        with tempfile.TemporaryDirectory(
            prefix="forge-publish-"
        ) as temporary_directory:
            temporary_path = Path(temporary_directory)

            _run_npm(
                [
                    npm_executable,
                    "pack",
                    f"--pack-destination={temporary_path}",
                ],
                cwd=directory,
                environment=environment,
                operation="pack",
            )

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

            _run_npm(
                [
                    npm_executable,
                    "publish",
                    str(archives[0]),
                    f"--registry={registry}",
                    f"--userconfig={npmrc}",
                    "--strict-ssl=true",
                    "--ignore-scripts",
                ],
                cwd=temporary_path,
                environment=environment,
                operation="publish",
            )

    except OSError as exc:
        raise PackageError("Unable to create or use temporary npm files.") from exc

    print()
    print("✓ NPM package published successfully.")
