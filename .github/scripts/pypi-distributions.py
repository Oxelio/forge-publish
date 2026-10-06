"""Verify GitHub release assets and stage only their wheel/sdist for PyPI."""

import argparse
import hashlib
import re
import shutil
from pathlib import Path


def stage_distributions(assets: Path, output: Path, tag: str) -> None:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError("Expected a stable vMAJOR.MINOR.PATCH release tag")
    version = tag[1:]
    distributions = {
        f"forge_publish-{version}-py3-none-any.whl",
        f"forge_publish-{version}.tar.gz",
    }
    expected = distributions | {"forge-publish.cdx.json"}
    files = expected | {"SHA256SUMS"}
    if {path.name for path in assets.iterdir()} != files:
        raise ValueError("Release assets must contain exactly the expected four files")
    if any(
        (assets / name).is_symlink() or not (assets / name).is_file() for name in files
    ):
        raise ValueError("Release assets must be regular files")
    hashes = {}
    for line in (assets / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match or match[2] not in expected or match[2] in hashes:
            raise ValueError("Invalid, duplicate or unexpected checksum entry")
        hashes[match[2]] = match[1]
    if hashes.keys() != expected:
        raise ValueError("Checksum manifest must cover every release artifact")
    for name, digest in hashes.items():
        with (assets / name).open("rb") as file:
            if hashlib.file_digest(file, "sha256").hexdigest() != digest:
                raise ValueError(f"Checksum mismatch: {name}")
    # Validate everything before creating a directory accepted by the upload action.
    output.mkdir(parents=True, exist_ok=False)
    for name in sorted(distributions):
        shutil.copyfile(assets / name, output / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    arguments = parser.parse_args()
    stage_distributions(arguments.assets, arguments.output, arguments.tag)


if __name__ == "__main__":
    main()
