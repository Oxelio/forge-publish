# forge-publish

A small command-line interface (CLI) for publishing packages to a [Forgejo](https://forgejo.org/) package registry.

`forge-publish` provides a single command-line tool for publishing different package types to Forgejo:

- Debian packages (`.deb`)
- Generic packages (archives, binaries, firmware, etc.)
- NPM packages

The goal is to make package publication predictable without requiring users to remember Forgejo API URLs, authentication details, or `curl` commands.

---

## Features

- Publish Debian packages
- Publish Generic packages
- Publish NPM packages
- Store Forgejo connection settings locally
- Store Forgejo tokens securely in the system keyring
- Support `FORGE_PUBLISH_TOKEN` for CI/CD environments
- Dry-run mode without requiring authentication
- Automatic Debian package metadata detection
- Parse Debian packages without `dpkg-deb`
- Support gzip, xz, zstd, bzip2, lzma, and uncompressed Debian control archives
- Use temporary NPM authentication configuration
- HTTP timeout and Forgejo error handling
- Clear package information before publication
- Cross-platform support
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

## Configuration

Configure the Forgejo connection once:

```bash
forge-publish config
```

The command asks for:

```text
Forgejo username:
Forgejo token:
```

The default Forgejo URL is:

```text
https://forge.fco.local
```

The default package owner is:

```text
Software
```

Both can be overridden:

```bash
forge-publish config \
    --url https://forge.example.com \
    --owner Software \
    --username my-user
```

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

It is stored separately in the operating system's credential store through the Python `keyring` package.

Depending on the platform, this typically uses facilities such as:

- Windows Credential Manager
- macOS Keychain
- a supported Linux secret-service backend

### Environment variable

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

## Security

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

---

# Debian packages

## Publish a Debian package

```bash
forge-publish deb servcli_1.9.3-0_i386.deb
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

### Supported control archive formats

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

The default distribution is:

```text
lenny
```

Override it with:

```bash
forge-publish deb package.deb \
    --distribution bookworm
```

Short option:

```bash
forge-publish deb package.deb -d bookworm
```

---

## Component

The default component is:

```text
main
```

Override it with:

```bash
forge-publish deb package.deb \
    --component main
```

Short option:

```bash
forge-publish deb package.deb -c main
```

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

```bash
forge-publish generic servcli.tar.gz \
    --package servcli \
    --version 1.9.3
```

This publishes the file to an endpoint such as:

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

## Specify the stored filename

By default, the source filename is used.

It can be overridden:

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

# NPM packages

NPM publication uses the standard `npm publish` command with Forgejo's NPM registry.

## Publish a package

Go to the directory containing `package.json`:

```bash
cd my-package
```

Then run:

```bash
forge-publish npm
```

Or specify the directory explicitly:

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
forge-publish deb servcli_1.9.3-0_i386.deb --dry-run
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

### HTTP 400

```text
invalid package or request
```

### HTTP 401

```text
authentication failed
```

### HTTP 403

```text
permission denied
```

### HTTP 404

```text
resource not found
```

### HTTP 409

```text
package/file already exists
```

### HTTP 413

```text
package/file is too large
```

### HTTP 429

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
forge-publish deb servcli_1.9.3-0_i386.deb
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

## Publish an NPM package

```bash
cd my-package
forge-publish npm
```

## Test without publishing

```bash
forge-publish deb servcli_1.9.3-0_i386.deb --dry-run
```

---

# Project structure

```text
forge-publish/
├── .gitattributes
├── .gitignore
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
    ├── test_client.py
    ├── test_config.py
    ├── test_deb.py
    ├── test_generic.py
    └── test_npm.py
```

### `cli.py`

Defines the command-line interface and converts expected application errors into user-friendly CLI errors.

### `config.py`

Handles:

- Forgejo URL, owner, and username configuration
- system keyring authentication
- environment-variable authentication
- interactive credential fallback

### `client.py`

Provides the common HTTP client used to communicate with Forgejo.

It handles:

- authentication
- uploads
- deletes
- HTTP timeouts
- Forgejo HTTP error messages

### `errors.py`

Defines the expected application exception hierarchy.

### `publishers/`

Contains registry-specific publication logic:

```text
publishers/
├── deb.py
├── generic.py
└── npm.py
```

### `tests/`

Contains unit tests for configuration, HTTP handling, Debian parsing, Generic publication, and NPM publication.

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

Activate it:

```bash
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Install the project and development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the tests:

```bash
pytest
```

Run the CLI directly:

```bash
python -m forge_publish --help
```

Or:

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
2. Extract package metadata when appropriate.
3. Build the Forgejo registry endpoint.
4. Use the common Forgejo client when using the HTTP API.
5. Support dry-run mode.
6. Raise application-specific errors for expected failures.
7. Avoid exposing authentication credentials.

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

The main objective is to make publication predictable:

```text
forge-publish <type> <package>
```

without requiring users to manually construct Forgejo API requests or registry-specific authentication configuration.

The project favors:

- simple modules
- explicit behavior
- minimal dependencies
- useful errors
- cross-platform operation
- secure credential handling
- easy extension without unnecessary abstractions

---

# Future package types

The architecture can be extended to support additional Forgejo package registries, for example:

- RPM
- PyPI
- Maven
- Cargo
- NuGet
- Composer
- Alpine
- Go packages
- Conan

These should be added as separate publishers rather than mixing registry-specific logic into the CLI.
