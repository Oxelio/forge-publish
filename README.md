# forge-publish

A small Python CLI for publishing packages to a Forgejo package registry.

Supported package types:

- Debian packages
- Generic packages
- NPM packages

The project focuses on explicit publication targets, secure credential handling, predictable CI/CD use, and a small implementation surface.

## Requirements

- Python 3.11 or newer
- Access to a Forgejo instance
- A Forgejo account and access token
- Node.js and npm only when publishing NPM packages

## Installation

```bash
python -m venv .venv
python -m pip install -e .
```

Then verify the installation:

```bash
forge-publish --help
```

## Quick start

Configure the Forgejo instance:

```bash
forge-publish config \
    --url https://forge.example.com \
    --owner Software \
    --username my-user
```

For CI/CD, provide the token through:

```text
FORGE_PUBLISH_TOKEN
```

Publish a Debian package:

```bash
forge-publish deb package.deb \
    --distribution bookworm \
    --component main
```

Publish a Generic package:

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 1.0.0
```

Publish an NPM package:

```bash
forge-publish npm
```

All publishing commands support `--dry-run`.

## Documentation

- [Configuration](docs/configuration.md)
- [Publishing packages](docs/publishing.md)
- [Security](docs/security.md)
- [Development](docs/development.md)
- [Release process](docs/releases.md)

## Development

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the checks:

```bash
pytest
ruff check .
ruff format --check .
pre-commit run --all-files
```

CI validates Python 3.11 through 3.14 and Windows compatibility.

## Design goals

`forge-publish` intentionally remains small. It favors:

- explicit environment and destination configuration
- natural defaults only when unambiguous
- secure credential handling
- useful errors
- cross-platform behavior
- direct, registry-specific publisher modules
- automated tests and release tooling

A plugin or factory architecture is not required for simple publisher additions.
