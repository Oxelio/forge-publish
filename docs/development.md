# Development

## Setup

Python 3.11 through 3.14 are supported.

```bash
python -m venv .venv
python -m pip install -e ".[dev,release]"
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

The Forgejo integration workflow starts a digest-pinned Forgejo 16.0.5 image with an ephemeral self-signed TLS certificate and validates real Generic, Debian, and NPM publication through the CLI. Node.js is pinned to 24.21.0, and the NPM publication test explicitly installs and verifies npm 10.5.2 so the documented minimum version is exercised against a real Forgejo registry. The workflow also verifies that Forgejo rejects invalid credentials.

For NPM, the integration fixture deliberately includes conflicting project-local NPM authentication and TLS settings plus conflicting `publishConfig.registry` and `publishConfig.strict-ssl` values. The publish must still use the temporary Forgejo credentials and verified TLS through Node's `NODE_EXTRA_CA_CERTS` mechanism.

Distribution verification installs the built wheel into a clean virtual environment and runs `pip check` before exercising the installed CLI. Release dependencies are validated with `pip check` as well.

Third-party GitHub Actions used by CI and release workflows are pinned to full commit SHAs, with the corresponding major version documented inline. Dependabot checks those GitHub Actions weekly so immutable pins can still be maintained through reviewable pull requests.

## Adding a publisher

Keep registry-specific behavior in `src/forge_publish/publishers/`.

A publisher should validate inputs, construct the Forgejo endpoint explicitly, support dry-run mode, avoid exposing credentials, and raise application-specific errors for expected failures.
