"""Generate a validated release SBOM from an installed wheel's runtime closure."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path
from urllib.parse import quote, urlsplit

import tomli_w
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[2]
FILENAME = "forge-publish.cdx.json"


def distribution_metadata(path: Path):
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            if len(names) != 1:
                raise ValueError("Expected one wheel metadata file")
            data = archive.read(names[0])
    else:
        with tarfile.open(path) as archive:
            members = [
                m
                for m in archive
                if m.name.count("/") == 1 and m.name.endswith("/PKG-INFO")
            ]
            if len(members) != 1:
                raise ValueError("Expected one source distribution metadata file")
            stream = archive.extractfile(members[0])
            if stream is None:
                raise ValueError("Source distribution metadata is not a file")
            data = stream.read()
    return BytesParser().parsebytes(data)


def runtime_closure(bom: dict) -> None:
    """Keep only dependencies reachable from the application, excluding bootstrap tools."""
    root_ref = bom["metadata"]["component"]["bom-ref"]
    graph = {d["ref"]: d for d in bom["dependencies"]}
    components = {c["bom-ref"]: c for c in bom["components"]}
    pending, reachable = [root_ref], set()
    while pending:
        ref = pending.pop()
        if ref in reachable:
            continue
        if ref not in graph or (ref != root_ref and ref not in components):
            raise ValueError("Incomplete runtime dependency graph")
        reachable.add(ref)
        pending.extend(graph[ref].get("dependsOn", []))
    bom["components"] = [c for c in bom["components"] if c["bom-ref"] in reachable]
    bom["dependencies"] = [d for d in bom["dependencies"] if d["ref"] in reachable]


def validate(bom: dict) -> str:
    text = json.dumps(bom, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if JsonStrictValidator(SchemaVersion.V1_6).validate_str(text) is not None:
        raise ValueError("SBOM does not conform to the CycloneDX 1.6 JSON schema")

    # Metadata comes from controlled distributions, never from CI environment
    # variables. Fail closed if a generator/tool update introduces private URLs.
    def check(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if key == "url":
                    parsed = urlsplit(item)
                    if (
                        parsed.scheme not in {"https", "http"}
                        or parsed.username
                        or parsed.password
                    ):
                        raise ValueError("SBOM contains a local or authenticated URL")
                check(item)
        elif isinstance(value, list):
            for item in value:
                check(item)

    check(bom)
    return text


def generate(runtime_python: Path, dist: Path, project_file: Path) -> Path:
    wheels, sources = sorted(dist.glob("*.whl")), sorted(dist.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("Expected exactly one wheel and one source distribution")
    metadata = distribution_metadata(wheels[0])
    source_metadata = distribution_metadata(sources[0])
    project = tomllib.loads(project_file.read_text(encoding="utf-8"))["project"]
    name, version = metadata["Name"], metadata["Version"]
    if (name, version) != (project["name"], project["version"]) or (name, version) != (
        source_metadata["Name"],
        source_metadata["Version"],
    ):
        raise ValueError("Project, wheel and source distribution versions/names differ")
    environment = json.loads(
        subprocess.check_output(
            [
                str(runtime_python),
                "-c",
                (
                    "import importlib.metadata as m,json,platform,sys; "
                    "d=m.distribution('forge-publish'); "
                    "print(json.dumps({'version':d.version,'requires':d.requires,"
                    "'python':platform.python_version(),'platform':sys.platform,"
                    "'isolated':sys.prefix!=sys.base_prefix and "
                    "not __import__('site').ENABLE_USER_SITE}))"
                ),
            ],
            text=True,
        )
    )
    if not environment["isolated"]:
        raise ValueError("SBOM requires an isolated runtime virtual environment")
    if environment["version"] != version or sorted(
        environment["requires"] or []
    ) != sorted(metadata.get_all("Requires-Dist", [])):
        raise ValueError(
            "Runtime environment does not contain the release wheel metadata"
        )
    # Use the built wheel's metadata, after Semantic Release's version bump.
    # Optional dev/release extras are intentionally outside this runtime profile.
    requirements = []
    for value in metadata.get_all("Requires-Dist", []):
        requirement = Requirement(value)
        if requirement.marker is None or "extra" not in str(requirement.marker):
            requirements.append(value)
    root_project = {
        "project": {
            "name": name,
            "version": version,
            "description": metadata["Summary"],
            "license": metadata["License-Expression"],
            "dependencies": requirements,
        }
    }
    with tempfile.TemporaryDirectory() as directory:
        manifest, output = (
            Path(directory) / "pyproject.toml",
            Path(directory) / "sbom.json",
        )
        manifest.write_text(tomli_w.dumps(root_project), encoding="utf-8")
        env = os.environ.copy()
        env.pop("SOURCE_DATE_EPOCH", None)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "cyclonedx_py",
                "environment",
                str(runtime_python),
                "--pyproject",
                str(manifest),
                "--spec-version",
                "1.6",
                "--output-format",
                "JSON",
                "--output-reproducible",
                "--validate",
                "--output-file",
                str(output),
            ],
            check=True,
            env=env,
        )
        bom = json.loads(output.read_text(encoding="utf-8"))
    runtime_closure(bom)
    root = bom["metadata"]["component"]
    if (root["name"], root["version"]) != (name, version):
        raise ValueError("Generated SBOM has the wrong release identity")
    root["purl"] = f"pkg:pypi/{canonicalize_name(name)}@{version}"
    root["externalReferences"] = [
        {
            "type": "distribution",
            "url": f"https://github.com/Oxelio/forge-publish/releases/download/v{version}/{quote(path.name)}",
            "hashes": [
                {
                    "alg": "SHA-256",
                    "content": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            ],
        }
        for path in [*wheels, *sources]
    ]
    bom["metadata"].setdefault("properties", []).extend(
        [
            {
                "name": "forge-publish:runtime-profile",
                "value": f"{environment['platform']}; Python {environment['python']}; base runtime extras only",
            },
            {
                "name": "forge-publish:dependency-policy",
                "value": "Resolved with requirements/tooling.txt; dependencies are not vendored; other platforms, Python versions and user resolutions may differ.",
            },
        ]
    )
    result = validate(bom)
    # Do not publish local paths from package metadata or future tool behavior.
    for path in (ROOT, runtime_python.absolute().parent.parent, Path.home()):
        if str(path).replace("\\", "/") in result.replace("\\\\", "/"):
            raise ValueError("SBOM contains a local absolute path")
    target = dist / FILENAME
    target.write_text(result, encoding="utf-8", newline="\n")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        required=True,
        type=Path,
        help="Clean runtime wheel environment's Python",
    )
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        target = generate(
            # Resolving Linux venv symlinks selects the global interpreter and
            # inventories tooling instead of the intended runtime environment.
            args.python.absolute(),
            args.dist.resolve(),
            ROOT / "pyproject.toml",
        )
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print(f"SBOM generation failed: {error}", file=sys.stderr)
        return 1
    print(f"Validated CycloneDX 1.6 SBOM: {target.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
