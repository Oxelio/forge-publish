# Security

## Forgejo tokens

Treat Forgejo access tokens as secrets.

Do not commit tokens to source code, scripts, documentation, project configuration, or CI workflow files.

For local use, `forge-publish` stores tokens through the Python `keyring` package. Depending on the platform, this typically maps to Windows Credential Manager, macOS Keychain, or a supported Linux secret-service backend.

For CI/CD, use `FORGE_PUBLISH_TOKEN` from the CI platform's secret store.

If a token is exposed, revoke it and create a new one.

## Configuration file

The TOML configuration contains only non-secret connection information. File permissions are restricted on a best-effort basis where the operating system supports it.

## TLS

TLS certificate verification is enabled by default.

The `--insecure` option for Debian and Generic packages disables certificate validation and therefore removes protection against man-in-the-middle attacks. Use it only in controlled environments.

## NPM credential isolation

NPM publication uses two phases:

1. `npm pack` runs before any Forgejo authentication file is created and without `FORGE_PUBLISH_TOKEN` in the subprocess environment.
2. `npm publish` receives a temporary `.npmrc` and publishes the generated archive with `--ignore-scripts`.

The temporary archive and authentication file are stored outside the project directory and removed automatically.
