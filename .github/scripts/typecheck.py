"""Run the locked Pyright CLI against this Python interpreter's environment."""

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    checker = ROOT / ".github/typecheck/node_modules/pyright/index.js"
    node = shutil.which("node")
    if node is None or not checker.is_file():
        print(
            "Install Node.js and run npm ci --prefix .github/typecheck --ignore-scripts",
            file=sys.stderr,
        )
        return 1
    return subprocess.run(
        [
            node,
            str(checker),
            "--project",
            str(ROOT / "pyproject.toml"),
            "--pythonpath",
            sys.executable,
            "--warnings",
        ],
        cwd=ROOT,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
