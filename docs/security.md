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

NPM publication requires stable npm 10.5.2 or newer and uses two phases:

1. `npm pack` runs in the package directory before any Forgejo authentication file is created.
2. `npm publish` runs from the temporary directory against the packed `.tgz`, receives a temporary `.npmrc`, forces `--registry` and `--strict-ssl=true`, and uses `--ignore-scripts`.

Before invoking npm, forge-publish removes `FORGE_PUBLISH_TOKEN`, `NPM_TOKEN`, `NODE_AUTH_TOKEN`, and all inherited `npm_config_*` variables from the subprocess environment. Normal network and trust variables such as `HTTPS_PROXY`, `NO_PROXY`, and `NODE_EXTRA_CA_CERTS` remain available.

Running the authenticated publish outside the package directory prevents a project-local `.npmrc` from overriding the temporary Forgejo credentials or TLS policy. Requiring stable npm 10.5.2 or newer ensures command-line publication settings take precedence over conflicting `publishConfig` values. The temporary archive and authentication file are removed automatically.
