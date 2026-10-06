import hashlib
import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github/scripts/pypi-distributions.py"
SPEC = importlib.util.spec_from_file_location("pypi_distributions", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.fixture
def assets(tmp_path: Path) -> Path:
    directory = tmp_path / "assets"
    directory.mkdir()
    artifacts = {
        "forge_publish-2.3.0-py3-none-any.whl": b"wheel\x00\xff",
        "forge_publish-2.3.0.tar.gz": b"sdist\x00\xff",
        "forge-publish.cdx.json": b'{"bomFormat":"CycloneDX"}',
    }
    for name, content in artifacts.items():
        (directory / name).write_bytes(content)
    (directory / "SHA256SUMS").write_text(
        "".join(
            f"{hashlib.sha256(content).hexdigest()}  {name}\n"
            for name, content in artifacts.items()
        ),
        encoding="utf-8",
    )
    return directory


def test_stages_only_byte_identical_distributions(assets: Path, tmp_path: Path) -> None:
    output = tmp_path / "dist"
    MODULE.stage_distributions(assets, output, "v2.3.0")
    assert {path.name for path in output.iterdir()} == {
        "forge_publish-2.3.0-py3-none-any.whl",
        "forge_publish-2.3.0.tar.gz",
    }
    for path in output.iterdir():
        assert path.read_bytes() == (assets / path.name).read_bytes()


@pytest.mark.parametrize(
    "name",
    [
        "forge_publish-2.3.0-py3-none-any.whl",
        "forge_publish-2.3.0.tar.gz",
        "forge-publish.cdx.json",
    ],
)
def test_rejects_tampering_before_staging(
    assets: Path, tmp_path: Path, name: str
) -> None:
    (assets / name).write_bytes(b"tampered")
    output = tmp_path / "dist"
    with pytest.raises(ValueError, match="Checksum mismatch"):
        MODULE.stage_distributions(assets, output, "v2.3.0")
    assert not output.exists()


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "traversal", "malformed"])
def test_rejects_invalid_manifest(assets: Path, tmp_path: Path, mutation: str) -> None:
    manifest = assets / "SHA256SUMS"
    lines = manifest.read_text(encoding="utf-8").splitlines(keepends=True)
    if mutation == "missing":
        lines.pop()
    elif mutation == "duplicate":
        lines.append(lines[0])
    elif mutation == "traversal":
        lines[0] = lines[0].replace("forge_publish-", "../forge_publish-")
    else:
        lines[0] = "invalid checksum\n"
    manifest.write_text("".join(lines), encoding="utf-8")
    output = tmp_path / "dist"
    with pytest.raises(ValueError):
        MODULE.stage_distributions(assets, output, "v2.3.0")
    assert not output.exists()


@pytest.mark.parametrize("tag", ["v2.3.1", "v2.3.0rc1", "2.3.0", "../v2.3.0"])
def test_rejects_wrong_or_unstable_release(
    assets: Path, tmp_path: Path, tag: str
) -> None:
    with pytest.raises(ValueError):
        MODULE.stage_distributions(assets, tmp_path / "dist", tag)


def test_rejects_extra_files_and_existing_upload_directory(
    assets: Path, tmp_path: Path
) -> None:
    output = tmp_path / "dist"
    output.mkdir()
    (output / "unreviewed.whl").write_bytes(b"unreviewed")
    with pytest.raises(FileExistsError):
        MODULE.stage_distributions(assets, output, "v2.3.0")
    assert (output / "unreviewed.whl").read_bytes() == b"unreviewed"
    (assets / "extra.whl").write_bytes(b"extra")
    with pytest.raises(ValueError, match="exactly"):
        MODULE.stage_distributions(assets, tmp_path / "new-dist", "v2.3.0")
