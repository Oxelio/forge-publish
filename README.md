# forge-publish

A small command-line interface (CLI) for publishing packages to a [Forgejo](https://forgejo.org/) package registry.

`forge-publish` provides a single command-line tool for publishing different package types to Forgejo:

* Debian packages (`.deb`)
* Generic packages (archives, binaries, firmware, etc.)
* NPM packages

The goal is to avoid having to remember Forgejo API URLs and `curl` commands for every package publication.

---

## Features

* Publish Debian packages
* Publish Generic packages
* Publish NPM packages
* Store Forgejo connection settings locally
* Authenticate using a Forgejo token
* Dry-run mode
* Automatic Debian package metadata detection
* Clear package information before publication
* Reusable command-line interface
* Designed to be easily extended with additional package registries

---

## Requirements

### Common

* Python 3.10 or newer
* Access to a Forgejo instance
* A Forgejo user account
* A Forgejo access token with permission to publish packages

### Debian packages

The `dpkg-deb` command must be available in `PATH`.

On Debian/Ubuntu:

```bash
sudo apt install dpkg
```

### NPM packages

Node.js and npm must be installed and available in `PATH`.

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
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

On Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Install the project:

```bash
pip install -e .
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

The Forgejo URL and package owner can also be specified:

```bash
forge-publish config \
    --url https://forge.example.com \
    --owner Software \
    --username StephWIP
```

The configuration is stored in:

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
username = "StephWIP"
token = "..."
```

The configuration file is created with restrictive permissions where supported.

### Environment variable

The Forgejo token can also be provided through:

```bash
export FORGE_PUBLISH_TOKEN="..."
```

This can be useful in CI/CD environments.

The environment variable takes precedence when a token is not stored in the configuration.

---

## Security

Never commit your Forgejo token to Git.

Do not put the token directly in:

* source code
* shell scripts
* CI configuration committed to the repository
* documentation
* command examples
* `.gitignore` exceptions

If a token is accidentally exposed, revoke it and generate a new one.

For CI/CD, prefer an environment variable or the CI secret-management mechanism.

---

# Usage

Show the available commands:

```bash
forge-publish --help
```

The available commands are:

```text
config
deb
generic
npm
```

---

# Debian packages

## Publish a Debian package

For example:

```bash
forge-publish deb servcli_1.9.3-0_i386.deb
```

The CLI reads the package metadata using `dpkg-deb`.

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

The default distribution is:

```text
lenny
```

The default component is:

```text
main
```

Both can be overridden.

### Distribution

```bash
forge-publish deb package.deb \
    --distribution bookworm
```

Short option:

```bash
forge-publish deb package.deb -d bookworm
```

### Component

```bash
forge-publish deb package.deb \
    --component main
```

Short option:

```bash
forge-publish deb package.deb -c main
```

### Example

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

* `.zip`
* `.tar.gz`
* binaries
* firmware
* installers
* documentation archives
* custom distribution files

## Publish a Generic package

```bash
forge-publish generic servcli.tar.gz \
    --package servcli \
    --version 1.9.3
```

This publishes the file to:

```text
/api/packages/Software/generic/servcli/1.9.3/servcli.tar.gz
```

### Specify the stored filename

By default, the original filename is used.

You can override it:

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 2.4.0 \
    --filename firmware-linux.bin
```

The Forgejo API endpoint is:

```text
PUT /api/packages/{owner}/generic/{package}/{version}/{filename}
```

---

# NPM packages

NPM publication uses the standard `npm publish` command and Forgejo's NPM registry.

## Publish a package

Go to the directory containing `package.json`:

```bash
cd my-package
```

Then:

```bash
forge-publish npm
```

Or specify the directory:

```bash
forge-publish npm ./my-package
```

The CLI reads `package.json` and displays the package name and version before publication.

Example:

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

The actual publication is performed using:

```bash
npm publish
```

This means the project must have npm installed.

---

# Dry-run

All publishing commands support dry-run mode.

Dry-run does not upload anything.

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

The dry-run mode is useful for checking the generated target before publishing.

---

# Exit codes

The command returns a non-zero exit code when publication fails.

Typical errors include:

```text
HTTP 401
```

Authentication failed.

```text
HTTP 403
```

The authenticated user does not have permission to publish the package.

```text
HTTP 404
```

The Forgejo endpoint or package registry was not found.

```text
HTTP 409
```

The package or file already exists.

```text
HTTP 400
```

The package or request is invalid.

This allows `forge-publish` to be used safely from shell scripts and CI/CD pipelines.

---

# Examples

## Publish servcli

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
├── pyproject.toml
├── README.md
├── .gitignore
└── src/
    └── forge_publish/
        ├── __init__.py
        ├── __main__.py
        ├── cli.py
        ├── client.py
        ├── config.py
        └── publishers/
            ├── __init__.py
            ├── deb.py
            ├── generic.py
            └── npm.py
```

### `cli.py`

Contains the command-line interface and commands.

### `config.py`

Handles the local Forgejo configuration.

### `client.py`

Provides the common HTTP client used to communicate with Forgejo.

### `publishers/`

Contains the implementation for each package registry.

```text
publishers/
├── deb.py
├── generic.py
└── npm.py
```

This structure makes it possible to add additional package formats later without changing the existing publishers.

---

# Development

Clone the repository:

```bash
git clone <repository-url>
cd forge-publish
```

Create the development environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the project in editable mode:

```bash
pip install -e .
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

The new publisher should:

1. Validate the package.
2. Extract package metadata when possible.
3. Build the Forgejo registry endpoint.
4. Use the common Forgejo client.
5. Support dry-run mode.
6. Report useful errors to the user.

---

# Design goals

`forge-publish` is intentionally small.

The project is not intended to replace package managers such as:

* `apt`
* `npm`
* `pip`
* `dnf`
* `cargo`

Instead, it provides a convenient interface for publishing packages to a Forgejo instance.

The main objective is to make package publication predictable:

```text
forge-publish <type> <package>
```

without requiring users to remember Forgejo API URLs or manually construct `curl` commands.

---

# Future package types

The architecture can be extended to support additional Forgejo package registries, for example:

* RPM
* PyPI
* Maven
* Cargo
* NuGet
* Composer
* Alpine
* Go packages
* Conan

These should be added as separate publishers rather than mixing registry-specific logic into the CLI.

---

# License

Add the project license here.

For example:

```text
MIT License
```

or replace this section with the license used by your project.
