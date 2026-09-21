import json
from pathlib import Path

from forge_publish.config import TOKEN_ENV_VAR, Config
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
        json.dumps(
            {
                "name": "example",
                "version": "1.0.0",
            }
        ),
        encoding="utf-8",
    )

    observed_npmrc: Path | None = None

    monkeypatch.setenv(
        TOKEN_ENV_VAR,
        "environment-secret-token",
    )

    monkeypatch.setattr(
        npm.shutil,
        "which",
        lambda _: "npm",
    )

    def fake_run(
        command,
        cwd,
        check,
        env,
    ):
        nonlocal observed_npmrc

        assert cwd == package_dir
        assert check is True

        # The forge-publish environment token must not be inherited by npm.
        assert TOKEN_ENV_VAR not in env

        userconfig = next(
            item.split("=", 1)[1]
            for item in command
            if item.startswith("--userconfig=")
        )

        observed_npmrc = Path(userconfig)

        content = observed_npmrc.read_text(encoding="utf-8")

        assert "secret-token" in content
        assert ("//forge.example.com/api/packages/Software/npm/:_authToken=") in content

    monkeypatch.setattr(
        npm.subprocess,
        "run",
        fake_run,
    )

    npm.publish(
        client=FakeClient(),
        directory=package_dir,
        dry_run=False,
    )

    assert observed_npmrc is not None
    assert not observed_npmrc.exists()
