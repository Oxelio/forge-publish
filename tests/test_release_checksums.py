import hashlib
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github/scripts/release-checksums.sh"
pytestmark = pytest.mark.skipif(
    sys.platform == "win32"
    or not shutil.which("bash")
    or not shutil.which("sha256sum"),
    reason="The release workflow uses Bash and GNU sha256sum on Linux",
)


def generate_checksums(directory: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), str(directory)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_release_checksums_cover_published_distributions(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    artifacts = {
        "forge_publish-2.0.1-py3-none-any.whl": b"wheel\x00\xff\n",
        "forge_publish-2.0.1.tar.gz": b"sdist\x00\xff\n",
        "forge-publish.cdx.json": b'{"bomFormat":"CycloneDX"}\n',
    }
    for name, content in artifacts.items():
        (dist / name).write_bytes(content)
    (dist / "unrelated.txt").write_text("must not be published")

    result = generate_checksums(dist)

    assert result.returncode == 0, result.stderr
    expected = "".join(
        f"{hashlib.sha256(content).hexdigest()}  {name}\n"
        for name, content in artifacts.items()
    )
    assert (dist / "SHA256SUMS").read_text() == expected
    assert generate_checksums(dist).returncode == 0
    assert (dist / "SHA256SUMS").read_text() == expected
    for name, content in artifacts.items():
        assert (dist / name).read_bytes() == content

    with (ROOT / "pyproject.toml").open("rb") as file:
        config = tomllib.load(file)
    patterns = config["tool"]["semantic_release"]["publish"]["dist_glob_patterns"]
    published = {path.name for pattern in patterns for path in tmp_path.glob(pattern)}
    assert published == {*artifacts, "SHA256SUMS"}

    (dist / next(iter(artifacts))).write_bytes(b"tampered")
    verification = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"],
        cwd=dist,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verification.returncode != 0
    assert "FAILED" in verification.stdout


@pytest.mark.parametrize(
    "present", [None, "package.whl", "package.tar.gz", "forge-publish.cdx.json"]
)
def test_release_checksums_reject_missing_distributions(
    tmp_path: Path, present: str | None
) -> None:
    if present:
        (tmp_path / present).write_bytes(b"artifact")

    assert generate_checksums(tmp_path).returncode != 0


def test_release_checksums_require_sbom(tmp_path: Path) -> None:
    (tmp_path / "package.whl").write_bytes(b"wheel")
    (tmp_path / "package.tar.gz").write_bytes(b"source")
    assert generate_checksums(tmp_path).returncode != 0
