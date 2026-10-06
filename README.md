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
- npm 11.0.0 or newer and a compatible Node.js runtime only when publishing NPM packages. npm 11.0.0 requires Node.js `^20.17.0 || >=22.9.0`. Prereleases of the minimum 11.0.0 release, such as 11.0.0-rc.0, are not supported; prereleases of later versions, such as 11.0.1-beta.1, satisfy the version check.

Forgejo compatibility targets are **15.x LTS** and **16.x stable**, with explicit
patch releases tested in the [compatibility matrix](.github/workflows/compatibility.yml).
A release line is supported only after its integration suite passes and while
it remains maintained upstream. See the [support policy](docs/development.md#forgejo-compatibility-and-support)
for validation, updates and end-of-life handling.

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

NPM pack lifecycle scripts are disabled by default. Build generated files before publishing, or use `--allow-pack-scripts` only for trusted packages. Enabling hooks can expose later publication credentials to background processes; see [NPM publishing](docs/publishing.md#npm).

All publishing commands support `--dry-run`.

## Documentation

- [Configuration](docs/configuration.md)
- [Publishing packages](docs/publishing.md)
- [Security](docs/security.md)
- [Vulnerability reporting and supported versions](.github/SECURITY.md)
- [Development](docs/development.md)
- [Release process](docs/releases.md)

## Development

Install development dependencies:

```bash
python -m pip install "pip==26.2.1"
python -m pip install \
    --constraint requirements/tooling.txt \
    --build-constraint requirements/build.txt \
    -e ".[dev]"
```

Run the checks:

```bash
pytest
ruff check .
ruff format --check .
pre-commit run --all-files
```

CI validates Python 3.11 through 3.14 and Windows compatibility.
It also checks production types with Pyright; see the
[type-checking setup and local command](docs/development.md#static-type-checking).

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

## License

This project is licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
