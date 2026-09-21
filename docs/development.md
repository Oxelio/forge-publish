# Development

## Setup

Python 3.11 through 3.14 are supported.

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

Activate the virtual environment using the normal command for your shell.

## Tests

```bash
pytest
```

Coverage and branch coverage are enabled through `pyproject.toml`, with an enforced minimum of 80%.

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
- Python 3.11, 3.12, 3.13, and 3.14 compatibility on Linux
- Windows compatibility on Python 3.11 and 3.14

The `Quality checks` job remains the required status check used by the repository ruleset.

A separate Forgejo integration workflow starts Forgejo 16.0.5 in Docker with an ephemeral self-signed TLS certificate and validates real Generic and Debian publication through the CLI.

NPM remains covered by unit tests in this integration workflow because authenticated NPM publication intentionally does not expose an insecure-TLS mode.

## Adding a publisher

Keep registry-specific behavior in `src/forge_publish/publishers/`.

A publisher should validate inputs, construct the Forgejo endpoint explicitly, support dry-run mode, avoid exposing credentials, and raise application-specific errors for expected failures.
