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

## Debian version marker

The `debian-binary` member is limited to 16 bytes before its payload is read, including during dry-run. The usual `2.0\n` marker and small whitespace variations remain supported; oversized, invalid, or truncated markers produce a package error. This marker limit does not restrict the size of `data.tar*` members, which are skipped while locating the control archive.

## NPM credential isolation

NPM publication requires npm 10.5.2 or newer and uses two phases:

1. `npm pack` runs in the package directory before any Forgejo authentication file is created.
2. `npm publish` runs from the temporary directory against the packed `.tgz`, receives a temporary `.npmrc`, forces `--registry` and `--strict-ssl=true`, and uses `--ignore-scripts`.

Before invoking npm, forge-publish removes `FORGE_PUBLISH_TOKEN`, `NPM_TOKEN`, `NODE_AUTH_TOKEN`, and all inherited `npm_config_*` variables from the subprocess environment. Normal network and trust variables such as `HTTPS_PROXY`, `NO_PROXY`, and `NODE_EXTRA_CA_CERTS` remain available.

The `npm_config_*` rejection is intentionally blanket and case-insensitive. forge-publish does not maintain an allowlist for npm configuration variables, because inherited npm configuration can affect publication-sensitive behavior and standard environment variables already cover the required network/trust cases without weakening registry, credential, or TLS isolation. This means npm-style proxy, CA, retry, timeout, or cache variables are stripped when expressed as `npm_config_*`; use standard variables such as `HTTPS_PROXY`, `NO_PROXY`, and `NODE_EXTRA_CA_CERTS` instead.

Running the authenticated publish outside the package directory prevents a project-local `.npmrc` from overriding the temporary Forgejo credentials or TLS policy. Requiring npm 10.5.2 or newer ensures command-line publication settings take precedence over conflicting `publishConfig` values. Prereleases of the minimum 10.5.2 release, such as `10.5.2-rc.0`, are rejected, while prereleases of later versions, such as `10.5.3-beta.1`, satisfy the implemented version check. The temporary archive and authentication file are removed automatically.
