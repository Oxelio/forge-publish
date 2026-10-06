"""Run a real NPM publication and reject credential leaks before showing output."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--allow-pack-scripts", action="store_true")
    parser.add_argument("--expect-auth-failure", action="store_true")
    args = parser.parse_args()
    token = os.environ.get("FORGE_PUBLISH_TOKEN")
    if not token:
        raise SystemExit("An integration token is required.")

    command = ["forge-publish", "npm", str(args.directory)]
    if args.allow_pack_scripts:
        command.append("--allow-pack-scripts")
    result = subprocess.run(command, capture_output=True, check=False)
    output = result.stdout + result.stderr
    # npm's default cache is used: forge-publish strips npm_config_* overrides.
    logs = Path.home() / ".npm" / "_logs"
    for data in [output, *(path.read_bytes() for path in logs.glob("*.log"))]:
        if token.encode() in data:
            raise SystemExit("A publication credential leaked into npm output or logs.")

    print(result.stdout.decode("utf-8", errors="replace"), end="")
    print(result.stderr.decode("utf-8", errors="replace"), end="")
    if args.expect_auth_failure:
        if (
            result.returncode == 0
            or b"npm publish failed with exit code" not in output
            or not any(code in output for code in (b"E401", b"E403"))
            or b"published successfully" in output
        ):
            raise SystemExit("Expected npm publication to reject authentication.")
    elif result.returncode != 0 or b"published successfully" not in output:
        raise SystemExit("Expected authenticated npm publication to succeed.")
    print("NPM output and debug logs contain no publication token.")


if __name__ == "__main__":
    main()
