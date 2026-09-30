# Development

## Setup

Python 3.11 through 3.14 are supported.

```bash
python -m venv .venv
python -m pip install "pip==26.2.1"
python -m pip install \
    --constraint requirements/tooling.txt \
    --build-constraint requirements/build.txt \
    -e ".[dev,release]"
```

Activate the virtual environment using the normal command for your shell.

## Tests

```bash
pytest
```

Coverage and branch coverage are enabled through `pyproject.toml`, with an enforced minimum of 85%.

Generate an HTML report with:

```bash
pytest --cov-report=html
```

## Linting and formatting

```bash
ruff check .
ruff format --check .
```

Apply automatic fixes with:

```bash
ruff check . --fix
ruff format .
```

## Pre-commit

Install hooks:

```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

The repository uses Conventional Commits.

Examples:

```text
feat(cli): add a command
fix(config): reject an invalid value
docs: clarify package publishing
test(client): cover an HTTP error
chore(ci): update the Python matrix
```

## CI

Pull requests run:

- Ruff linting
- Ruff formatting verification
- unit tests with coverage
- wheel and sdist build verification
- Python 3.11, 3.12, and 3.13 compatibility jobs on Linux
- the full quality suite on Python 3.14
- Windows compatibility on Python 3.11 and 3.14

The repository ruleset continues to require the `Quality checks` status. CI now runs the main quality suite, Forgejo integration, Linux compatibility matrix, and Windows compatibility matrix in parallel. A final job named `Quality checks` depends on all four groups and fails unless every group succeeds.

The Forgejo integration workflow starts a digest-pinned Forgejo 16.0.5 image with an ephemeral self-signed TLS certificate and validates real Generic, Debian, and NPM publication through the CLI. Node.js is pinned to 24.21.0. NPM publication is exercised twice against the same Forgejo instance: once with the npm version bundled with that pinned Node.js runtime and once after explicitly installing and verifying the minimum supported npm 10.5.2. The two publications use distinct package versions so both compatibility paths are validated without hard-coding an assumed bundled npm version. The workflow also verifies that Forgejo rejects invalid credentials.

For NPM, both compatibility publications deliberately include conflicting project-local NPM authentication and TLS settings plus conflicting `publishConfig.registry` and `publishConfig.strict-ssl` values. Each publish must still use the temporary Forgejo credentials and verified TLS through Node's `NODE_EXTRA_CA_CERTS` mechanism.

Distribution verification installs both the built wheel and the built source distribution into separate clean virtual environments, runs `pip check`, and exercises the installed CLI from each artifact. Release dependencies are validated with `pip check` as well.

Development, CI, integration, and release environments use `requirements/tooling.txt` as an exact constraints set while `pyproject.toml` keeps compatible dependency ranges for normal forge-publish users. Isolated PEP 517 builds use the separate `requirements/build.txt` build constraint so the build backend is deterministic as well. pip itself is pinned in these controlled environments.

## Updating Python dependencies

Python dependency updates should be isolated in a dedicated dependency PR:

1. review the direct dependency ranges in `pyproject.toml`;
2. refresh exact versions in `requirements/tooling.txt` and, when needed, `requirements/build.txt`;
3. use a clean environment and install `.[dev,release]` with the candidate constraints;
4. run `pip check`, the local quality checks, and the full GitHub Actions matrix;
5. verify the real Forgejo integration before merging.

The tooling constraints intentionally include the union of relevant conditional dependencies for Python 3.11-3.14, Linux, and Windows. A constraint does not cause a package to be installed by itself; it fixes the version only when that package is required in the current environment.

Dependabot checks both the `pip` ecosystem and GitHub Actions weekly, so dependency changes arrive as reviewable pull requests rather than silently changing CI resolution. Third-party GitHub Actions remain pinned to full commit SHAs, with the corresponding major version documented inline.

## Adding a publisher

Keep registry-specific behavior in `src/forge_publish/publishers/`.

A publisher should validate inputs, construct the Forgejo endpoint explicitly, support dry-run mode, avoid exposing credentials, and raise application-specific errors for expected failures.
