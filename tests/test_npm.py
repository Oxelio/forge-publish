import json
from pathlib import Path

from forge_publish.config import Config
from forge_publish.publishers import npm


class FakeClient:
    def __init__(self) -> None:
        self.config = Config(
            url="https://forge.example.com",
            owner="Software",
            username="user",
            token="secret-token",
        )


def test_npm_uses_temporary_userconfig(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package_dir = tmp_path / "package"
    package_dir.mkdir()
    (package_dir / "package.json").write_text(
        json.dumps({"name": "example", "version": "1.0.0"}),
        encoding="utf-8",
    )

    observed_npmrc: Path | None = None

    monkeypatch.setattr(npm.shutil, "which", lambda _: "npm")

    def fake_run(command, cwd, check):
        nonlocal observed_npmrc
        userconfig = next(
            item.split("=", 1)[1]
            for item in command
            if item.startswith("--userconfig=")
        )
        observed_npmrc = Path(userconfig)
        content = observed_npmrc.read_text(encoding="utf-8")
        assert "secret-token" in content
        assert (
            "//forge.example.com/api/packages/Software/npm/:_authToken="
            in content
        )

    monkeypatch.setattr(npm.subprocess, "run", fake_run)

    npm.publish(FakeClient(), package_dir)

    assert observed_npmrc is not None
    assert not observed_npmrc.exists()
