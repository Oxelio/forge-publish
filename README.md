# forge-publish

A small command-line interface (CLI) for publishing packages to a [Forgejo](https://forgejo.org/) package registry.

`forge-publish` provides a consistent interface for publishing different package types to Forgejo:

- Debian packages (`.deb`)
- Generic packages (archives, binaries, firmware, etc.)
- NPM packages

The goal is to make package publication predictable and explicit where it matters, without requiring users to manually construct Forgejo API URLs, authentication configuration, or `curl` commands.

---

## Features

- Publish Debian packages
- Publish Generic packages
- Publish NPM packages
- Store Forgejo connection settings locally
- Store Forgejo tokens securely in the system keyring
- Support `FORGE_PUBLISH_TOKEN` for CI/CD environments
- Avoid arbitrary environment and publication-target defaults
- Use natural defaults where behavior is unambiguous
- Dry-run mode without requiring authentication
- Automatic Debian package metadata detection
- Parse Debian packages without `dpkg-deb`
- Support gzip, xz, zstd, bzip2, lzma, and uncompressed Debian control archives
- Use temporary NPM authentication configuration
- HTTP timeout and Forgejo error handling
- Optional insecure TLS mode for Debian and Generic package publishing
- Clear package information before publication
- Cross-platform support
- Automated tests with branch coverage
- Ruff linting and formatting
- Pre-commit quality checks
- Conventional Commit validation
- Designed to be extended with additional Forgejo package registries

---

## Requirements

### Common

- Python 3.14 or newer
- Access to a Forgejo instance
- A Forgejo user account
- A Forgejo access token with permission to publish packages

No external Debian tooling such as `dpkg-deb` is required.

### NPM packages

Node.js and npm must be installed and available in `PATH` to publish NPM packages.

Check with:

```bash
node --version
npm --version
```

---

## Installation

### From source

Clone the repository:

```bash
git clone <repository-url>
cd forge-publish
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the project:

```bash
python -m pip install -e .
```

The `forge-publish` command is then available:

```bash
forge-publish --help
```

---

# Configuration

Forgejo connection settings must be configured explicitly before publishing packages.

Run:

```bash
forge-publish config
```

The command asks for:

```text
Forgejo URL:
Forgejo owner:
Forgejo username:
Forgejo token:
```

For example:

```text
Forgejo URL: https://forge.example.com
Forgejo owner: Software
Forgejo username: my-user
Forgejo token:
```

The configuration can also be supplied non-interactively:

```bash
forge-publish config \
    --url https://forge.example.com \
    --owner Software \
    --username my-user
```

There are no built-in defaults for the Forgejo URL or package owner.

The non-secret configuration is stored in:

```text
~/.config/forge-publish/config.toml
```

On Windows:

```text
%USERPROFILE%\.config\forge-publish\config.toml
```

Example:

```toml
url = "https://forge.example.com"
owner = "Software"
username = "my-user"
```

The Forgejo token is **not stored in `config.toml`**.

It is stored separately in the operating system credential store through the Python `keyring` package.

Depending on the platform, this typically uses facilities such as:

- Windows Credential Manager
- macOS Keychain
- a supported Linux secret-service backend

## Environment variable

The Forgejo token can also be supplied through:

```text
FORGE_PUBLISH_TOKEN
```

Linux/macOS:

```bash
export FORGE_PUBLISH_TOKEN="..."
```

PowerShell:

```powershell
$env:FORGE_PUBLISH_TOKEN = "..."
```

This is particularly useful in CI/CD environments.

When present, the environment variable takes priority over the token stored in the system keyring.

When no environment token is available, `forge-publish` checks the system keyring and falls back to an interactive token prompt when necessary.

---

# Security

Forgejo access tokens are secrets.

Never commit them to Git or store them directly in:

- source code
- shell scripts
- documentation
- committed CI configuration
- command examples
- project configuration files

For local interactive use, prefer the system keyring.

For CI/CD, prefer `FORGE_PUBLISH_TOKEN` through the CI platform's secret-management mechanism.

If a token is accidentally exposed, revoke it and generate a new one.

## TLS certificate verification

TLS certificate verification is enabled during normal publication.

For development environments or Forgejo instances using certificates that cannot be validated by the local trust store, Debian and Generic package publishing can explicitly disable TLS certificate verification with:

```text
--insecure
```

For example:

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 1.0.0 \
    --insecure
```

or:

```bash
forge-publish deb package.deb \
    --distribution lenny \
    --component main \
    --insecure
```

Using `--insecure` disables server certificate verification and therefore removes protection against man-in-the-middle attacks.

It should only be used in controlled environments. Configuring the appropriate certificate authority in the operating system trust store is preferred whenever possible.

---

# Usage

Show the available commands:

```bash
forge-publish --help
```

Available commands:

```text
config
deb
generic
npm
```

Environment-specific and publication-target values are explicit when no natural unambiguous value can be inferred.

Natural defaults such as the source filename for Generic packages or the current directory for NPM packages are preserved.

---

# Debian packages

## Publish a Debian package

A Debian publication requires both the target distribution and component:

```bash
forge-publish deb servcli_1.9.3-0_i386.deb \
    --distribution lenny \
    --component main
```

Short options are also available:

```bash
forge-publish deb servcli_1.9.3-0_i386.deb \
    -d lenny \
    -c main
```

`forge-publish` reads the Debian package directly in Python.

It extracts metadata from the package control archive without requiring `dpkg-deb`.

Example output:

```text
Debian package
--------------
Name         : servcli
Version      : 1.9.3-0
Architecture : i386
Distribution : lenny
Component    : main
URL          : https://forge.example.com/api/packages/Software/debian/pool/lenny/main/upload

✓ Debian package published successfully.
```

## Supported control archive formats

The Debian metadata reader supports:

```text
control.tar
control.tar.gz
control.tar.xz
control.tar.zst
control.tar.bz2
control.tar.lzma
```

The package is read sequentially and the potentially large `data.tar.*` payload does not need to be loaded into memory to extract package metadata.

---

## Distribution

The target distribution must be supplied explicitly:

```bash
forge-publish deb package.deb \
    --distribution bookworm \
    --component main
```

Short option:

```bash
forge-publish deb package.deb \
    -d bookworm \
    -c main
```

No distribution is selected automatically.

---

## Component

The target component must also be supplied explicitly:

```bash
forge-publish deb package.deb \
    --distribution bookworm \
    --component main
```

Short option:

```bash
forge-publish deb package.deb \
    -d bookworm \
    -c main
```

No component is selected automatically.

---

## Disable TLS certificate verification

TLS certificate verification can be explicitly disabled with:

```bash
forge-publish deb package.deb \
    --distribution lenny \
    --component main \
    --insecure
```

This should only be used in controlled environments where the Forgejo server certificate cannot be validated by the local trust store.

Prefer configuring the appropriate certificate authority instead of disabling certificate verification whenever possible.

---

## Complete example

```bash
forge-publish deb servcli_1.9.3-0_i386.deb \
    --distribution lenny \
    --component main
```

The corresponding Forgejo API endpoint is:

```text
PUT /api/packages/{owner}/debian/pool/{distribution}/{component}/upload
```

---

# Generic packages

Generic packages are useful for files that do not belong to a specific package ecosystem.

Examples include:

- `.zip`
- `.tar.gz`
- binaries
- firmware
- installers
- documentation archives
- custom distribution files

## Publish a Generic package

A Generic publication requires a package name and version:

```bash
forge-publish generic servcli.tar.gz \
    --package servcli \
    --version 1.9.3
```

By default, the source filename is used as the filename stored in Forgejo.

For example:

```text
/api/packages/Software/generic/servcli/1.9.3/servcli.tar.gz
```

The package name and stored filename are validated before publication.

Allowed characters are:

```text
A-Z
a-z
0-9
.
-
+
_
```

The version must be non-empty and must not contain leading or trailing whitespace.

URL path components are percent-encoded when required.

---

## Stored filename

By default, the source filename is preserved.

For example:

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 2.4.0
```

stores the file as:

```text
firmware.bin
```

The stored filename can be overridden explicitly:

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 2.4.0 \
    --filename firmware-linux.bin
```

The Forgejo endpoint is:

```text
PUT /api/packages/{owner}/generic/{package}/{version}/{filename}
```

---

## Disable TLS certificate verification

TLS certificate verification can be explicitly disabled with:

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 2.4.0 \
    --insecure
```

When enabled, a warning is displayed before publication.

This option should only be used in controlled environments. Configuring the appropriate certificate authority in the local trust store is preferred.

---

# NPM packages

NPM publication uses the standard `npm publish` command with Forgejo's NPM registry.

## Publish a package

By default, the current directory is used:

```bash
forge-publish npm
```

This is equivalent to:

```bash
forge-publish npm .
```

Another package directory can be specified explicitly:

```bash
forge-publish npm ./my-package
```

`forge-publish` reads `package.json` and validates that a package name and version are present.

Example output:

```text
NPM package
-----------
Name     : @software/my-package
Version  : 1.2.3
Registry : https://forge.example.com/api/packages/Software/npm/

✓ NPM package published successfully.
```

The Forgejo NPM registry endpoint is:

```text
/api/packages/{owner}/npm/
```

---

## NPM authentication

`forge-publish` creates a temporary `.npmrc` containing the Forgejo registry and authentication token.

Conceptually:

```ini
registry=https://forge.example.com/api/packages/Software/npm/
//forge.example.com/api/packages/Software/npm/:_authToken=<token>
```

The temporary configuration is passed explicitly to npm:

```text
npm publish --registry=<registry> --userconfig=<temporary .npmrc>
```

The `.npmrc` is created outside the project directory and removed automatically after publication.

The authentication token is not passed directly as a command-line argument.

---

# Dry-run

All publishing commands support dry-run mode.

Dry-run:

- validates local package metadata
- builds and displays the target Forgejo endpoint
- does not upload anything
- does not require a Forgejo token
- does not access the system keyring

## Debian

```bash
forge-publish deb servcli_1.9.3-0_i386.deb \
    --distribution lenny \
    --component main \
    --dry-run
```

Example:

```text
Debian package
--------------
Name         : servcli
Version      : 1.9.3-0
Architecture : i386
Distribution : lenny
Component    : main
URL          : https://forge.example.com/api/packages/Software/debian/pool/lenny/main/upload

DRY RUN
-------
PUT  : https://forge.example.com/api/packages/Software/debian/pool/lenny/main/upload
FILE : servcli_1.9.3-0_i386.deb
```

## Generic

```bash
forge-publish generic servcli.tar.gz \
    --package servcli \
    --version 1.9.3 \
    --dry-run
```

## NPM

```bash
forge-publish npm --dry-run
```

Example:

```text
NPM package
-----------
Name     : @software/my-package
Version  : 1.2.3
Registry : https://forge.example.com/api/packages/Software/npm/

DRY RUN
-------
npm publish --registry=https://forge.example.com/api/packages/Software/npm/ --userconfig=<temporary .npmrc>
```

---

# Error handling

`forge-publish` returns a non-zero exit code when configuration, validation, authentication, or publication fails.

Common Forgejo HTTP errors include:

## HTTP 400

```text
invalid package or request
```

## HTTP 401

```text
authentication failed
```

## HTTP 403

```text
permission denied
```

## HTTP 404

```text
resource not found
```

## HTTP 409

```text
package/file already exists
```

## HTTP 413

```text
package/file is too large
```

## HTTP 429

```text
too many requests
```

Server-side `5xx` responses are reported as Forgejo server errors.

Forgejo response messages are included when available and truncated when excessively large.

HTTP requests use explicit connection and transfer timeouts to avoid hanging indefinitely.

---

# Examples

## Publish a Debian package

```bash
forge-publish deb servcli_1.9.3-0_i386.deb \
    --distribution lenny \
    --component main
```

## Publish a binary archive

```bash
forge-publish generic servcli-1.9.3.tar.gz \
    --package servcli \
    --version 1.9.3
```

## Publish firmware

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 5.2.1
```

## Publish firmware under another filename

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 5.2.1 \
    --filename firmware-linux.bin
```

## Publish to a server with unverified TLS

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 5.2.1 \
    --insecure
```

## Publish an NPM package from the current directory

```bash
forge-publish npm
```

## Publish an NPM package from another directory

```bash
forge-publish npm ./my-package
```

## Test without publishing

```bash
forge-publish deb servcli_1.9.3-0_i386.deb \
    --distribution lenny \
    --component main \
    --dry-run
```

---

# Project structure

```text
forge-publish/
├── .gitattributes
├── .gitignore
├── .pre-commit-config.yaml
├── README.md
├── pyproject.toml
├── src/
│   └── forge_publish/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── client.py
│       ├── config.py
│       ├── errors.py
│       └── publishers/
│           ├── __init__.py
│           ├── deb.py
│           ├── generic.py
│           └── npm.py
└── tests/
    ├── test_cli.py
    ├── test_client.py
    ├── test_config.py
    ├── test_deb.py
    ├── test_generic.py
    └── test_npm.py
```

## `cli.py`

Defines the command-line interface and converts expected application errors into user-friendly CLI errors.

It also handles command-specific options such as dry-run mode and insecure TLS configuration.

Environment-specific and destination-specific parameters are intentionally explicit when no natural value can be inferred.

## `config.py`

Handles:

- Forgejo URL, owner, and username configuration
- system keyring authentication
- environment-variable authentication
- interactive credential fallback

The Forgejo URL and owner are explicitly configured and persisted rather than supplied through application defaults.

## `client.py`

Provides the common HTTP client used to communicate with Forgejo.

It handles:

- authentication
- uploads
- deletes
- TLS certificate verification
- HTTP timeouts
- Forgejo HTTP error messages

Behavioral parameters such as dry-run and TLS verification are explicitly supplied by callers.

## `errors.py`

Defines the expected application exception hierarchy.

## `publishers/`

Contains registry-specific publication logic:

```text
publishers/
├── deb.py
├── generic.py
└── npm.py
```

## `tests/`

Contains unit tests for the CLI, configuration, HTTP handling, Debian parsing, Generic publication, and NPM publication.

## `.pre-commit-config.yaml`

Defines local Git hooks used during development:

- Ruff linting and automatic fixes before commits
- Ruff formatting before commits
- Conventional Commit validation through Commitizen

---

# Development

Clone the repository:

```bash
git clone <repository-url>
cd forge-publish
```

Create a Python 3.14 virtual environment:

```bash
python -m venv .venv
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Development dependencies include:

- pytest
- pytest-cov
- Ruff
- pre-commit
- Commitizen

---

## Git hooks

Install the pre-commit hook used for linting and formatting:

```bash
pre-commit install
```

Install the `commit-msg` hook used to validate Conventional Commits:

```bash
pre-commit install --hook-type commit-msg
```

After installation, normal commits automatically run the configured checks.

For example:

```bash
git commit -m "fix(config): validate Forgejo URL"
```

The `pre-commit` stage runs:

```text
ruff check --fix
ruff format
```

The `commit-msg` stage validates the commit message with Commitizen.

Commit messages must follow the Conventional Commits format, for example:

```text
feat(cli): add config command
fix(config): reject invalid URLs
docs(readme): update development setup
test(client): add HTTP error coverage
chore(dev): update Ruff configuration
```

A non-conforming message such as:

```text
update stuff
```

is rejected.

If Ruff modifies files automatically, the commit is stopped so the changes can be reviewed and staged:

```bash
git add .
git commit
```

To run all configured pre-commit hooks manually against the repository:

```bash
pre-commit run --all-files
```

---

## Tests

Run the full test suite:

```bash
pytest
```

Coverage and branch coverage are enabled automatically through `pyproject.toml`.

The test output includes:

- statement coverage
- branch coverage
- partially covered branches
- missing lines

To generate an HTML coverage report:

```bash
pytest --cov-report=html
```

The report is generated in:

```text
htmlcov/
```

Open:

```text
htmlcov/index.html
```

in a browser to inspect coverage per file and line.

---

## Linting

Check the repository with Ruff:

```bash
ruff check .
```

Automatically fix supported lint issues:

```bash
ruff check . --fix
```

---

## Formatting

Check formatting without modifying files:

```bash
ruff format --check .
```

Format the repository:

```bash
ruff format .
```

---

## Recommended local checks

Before pushing changes, run:

```bash
pytest
ruff check .
ruff format --check .
pre-commit run --all-files
```

---

## Run the CLI

Run the CLI directly:

```bash
python -m forge_publish --help
```

Or use the installed command:

```bash
forge-publish --help
```

---

# Adding a new package type

Package publishers are intentionally separated.

For example, adding RPM support could result in:

```text
publishers/
├── deb.py
├── generic.py
├── npm.py
└── rpm.py
```

A new publisher should generally:

1. Validate its input.
2. Avoid arbitrary defaults for environment-specific or publication-target parameters.
3. Use natural inferred values only when they are unambiguous.
4. Extract package metadata when appropriate.
5. Build the Forgejo registry endpoint.
6. Use the common Forgejo client when using the HTTP API.
7. Support dry-run mode.
8. Raise application-specific errors for expected failures.
9. Avoid exposing authentication credentials.

No plugin or factory architecture is required for simple publisher additions.

---

# Design goals

`forge-publish` is intentionally small.

The project is not intended to replace package managers such as:

- `apt`
- `npm`
- `pip`
- `dnf`
- `cargo`

Instead, it provides a consistent interface for publishing packages to Forgejo.

The project favors:

- explicit environment configuration
- explicit destination-specific parameters
- natural and unambiguous inferred defaults
- explicit internal behavior
- simple modules
- minimal dependencies
- useful errors
- cross-platform operation
- secure credential handling
- automated quality checks
- easy extension without unnecessary abstractions

Configuration that identifies the Forgejo instance is persisted explicitly.

Publication-target values such as Debian distribution and component must be provided explicitly.

Natural values may still be inferred when they are unambiguous, such as using the source filename for Generic packages or the current directory for NPM publication.
