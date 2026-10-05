import copy
import hashlib
import importlib.util
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/release-sbom.py"
spec = importlib.util.spec_from_file_location("release_sbom", SCRIPT)
assert spec and spec.loader
sbom = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sbom)


def sample_bom():
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "forge-publish",
                "version": "9.8.7",
                "bom-ref": "root",
            }
        },
        "components": [
            {"type": "library", "name": name, "version": version, "bom-ref": name}
            for name, version in [
                ("requests", "2.34.2"),
                ("urllib3", "2.8.0"),
                ("pip", "26.2.1"),
                ("pytest", "9.1.1"),
            ]
        ],
        "dependencies": [
            {"ref": "root", "dependsOn": ["requests"]},
            {"ref": "requests", "dependsOn": ["urllib3"]},
            {"ref": "urllib3"},
            {"ref": "pip"},
            {"ref": "pytest"},
        ],
    }


@pytest.fixture
def release(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    metadata = (
        b"Metadata-Version: 2.4\nName: forge-publish\nVersion: 9.8.7\n"
        b"Summary: Test CLI\nLicense-Expression: Apache-2.0\n"
        b"Requires-Dist: requests>=2.31\n"
        b'Requires-Dist: pytest>=8; extra == "dev"\n\n'
    )
    wheel = dist / "forge_publish-9.8.7-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("forge_publish-9.8.7.dist-info/METADATA", metadata)
    source = dist / "forge_publish-9.8.7.tar.gz"
    with tarfile.open(source, "w:gz") as archive:
        member = tarfile.TarInfo("forge_publish-9.8.7/PKG-INFO")
        member.size = len(metadata)
        archive.addfile(member, io.BytesIO(metadata))
    project = tmp_path / "pyproject.toml"
    project.write_text('[project]\nname="forge-publish"\nversion="9.8.7"\n')
    profile = {
        "version": "9.8.7",
        "requires": ["requests>=2.31", 'pytest>=8; extra == "dev"'],
        "python": "3.14.0",
        "platform": "linux",
        "isolated": True,
    }
    monkeypatch.setattr(
        sbom.subprocess, "check_output", lambda *a, **kw: json.dumps(profile)
    )

    def generator(command, **kwargs):
        manifest = Path(command[command.index("--pyproject") + 1])
        assert sbom.tomllib.loads(manifest.read_text())["project"]["dependencies"] == [
            "requests>=2.31"
        ]
        assert "--validate" in command
        assert "SOURCE_DATE_EPOCH" not in kwargs["env"]
        output = Path(command[command.index("--output-file") + 1])
        output.write_text(json.dumps(sample_bom()))

    monkeypatch.setattr(sbom.subprocess, "run", generator)
    return dist, project, profile


def test_release_sbom_identifies_bumped_artifacts_and_runtime_closure(
    release, monkeypatch
):
    dist, project, _ = release
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "123")
    monkeypatch.setenv("GH_TOKEN", "must-not-enter-sbom")
    python = dist.parent / "runtime/bin/python"
    path = sbom.generate(python, dist, project)
    content = path.read_bytes()
    bom = json.loads(content)
    root = bom["metadata"]["component"]
    assert root["version"] == "9.8.7"
    assert root["purl"] == "pkg:pypi/forge-publish@9.8.7"
    assert {c["name"] for c in bom["components"]} == {"requests", "urllib3"}
    assert {d["ref"] for d in bom["dependencies"]} == {"root", "requests", "urllib3"}
    for artifact, reference in zip(
        sorted(dist.glob("*.whl")) + sorted(dist.glob("*.tar.gz")),
        root["externalReferences"],
        strict=True,
    ):
        assert reference["url"].endswith(f"/v9.8.7/{artifact.name}")
        assert reference["hashes"] == [
            {
                "alg": "SHA-256",
                "content": hashlib.sha256(artifact.read_bytes()).hexdigest(),
            }
        ]
    assert "must-not-enter-sbom" not in content.decode()
    assert "linux; Python 3.14.0" in content.decode()
    assert str(dist.parent) not in content.decode()
    assert sbom.generate(python, dist, project).read_bytes() == content


@pytest.mark.parametrize("target", ["project", "environment"])
def test_release_sbom_rejects_wrong_version(release, target):
    dist, project, profile = release
    if target == "project":
        project.write_text('[project]\nname="forge-publish"\nversion="1.0.0"\n')
    else:
        profile["version"] = "1.0.0"
    with pytest.raises(ValueError, match="metadata|versions"):
        sbom.generate(dist.parent / "python", dist, project)
    assert not (dist / sbom.FILENAME).exists()


def test_release_sbom_rejects_wrong_runtime_requirements(release):
    dist, project, profile = release
    profile["requires"] = ["requests>=1"]
    with pytest.raises(ValueError, match="metadata"):
        sbom.generate(dist.parent / "python", dist, project)


def test_release_sbom_requires_isolated_environment(release):
    dist, project, profile = release
    profile["isolated"] = False
    with pytest.raises(ValueError, match="isolated"):
        sbom.generate(dist.parent / "python", dist, project)


def test_cli_preserves_virtual_environment_interpreter_symlink(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime-python"
    try:
        runtime.symlink_to(sys.executable)
    except OSError:
        pytest.skip("Creating a symlink requires local Windows privileges")
    observed = []

    def generate(python, dist, project):
        observed.append(python)
        return dist / sbom.FILENAME

    monkeypatch.setattr(sbom, "generate", generate)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--python", str(runtime)])
    assert sbom.main() == 0
    assert observed == [runtime.absolute()]
    assert observed[0] != runtime.resolve()


@pytest.mark.parametrize("missing", ["*.whl", "*.tar.gz"])
def test_release_sbom_requires_both_artifacts(release, missing):
    dist, project, _ = release
    next(dist.glob(missing)).unlink()
    with pytest.raises(ValueError, match="exactly one"):
        sbom.generate(dist.parent / "python", dist, project)


def test_runtime_closure_rejects_missing_transitive_component():
    bom = sample_bom()
    bom["components"] = [c for c in bom["components"] if c["name"] != "urllib3"]
    with pytest.raises(ValueError, match="Incomplete"):
        sbom.runtime_closure(bom)


def test_validate_rejects_invalid_schema():
    bom = sample_bom()
    del bom["bomFormat"]
    with pytest.raises(ValueError, match="schema"):
        sbom.validate(bom)


@pytest.mark.parametrize(
    "url",
    ["file:///home/runner/private.whl", "https://user:secret@example.org/package"],
)
def test_validate_rejects_local_or_authenticated_urls(url):
    bom = copy.deepcopy(sample_bom())
    bom["metadata"]["component"]["externalReferences"] = [
        {"type": "distribution", "url": url}
    ]
    with pytest.raises(ValueError, match="local or authenticated"):
        sbom.validate(bom)
