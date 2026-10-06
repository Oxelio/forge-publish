# Security

To report a suspected vulnerability privately or check which releases receive
security fixes, see the [security policy](../.github/SECURITY.md). This page
describes the CLI's security behavior.

## Code scanning

GitHub CodeQL default setup analyzes Python on `main`, pull requests and a weekly
schedule. Maintainers review alerts in [Security and quality > Code scanning](https://github.com/Oxelio/forge-publish/security/code-scanning).
See the [development workflow](development.md#codeql-code-scanning) for scan
configuration, baseline verification and evidence-based alert triage.

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

## Debian control archive resources

Control archives are limited to 8 MiB of compressed input, 16 MiB of decompressed tar data, and 1 MiB for the control file. XZ and LZMA-alone decoding also has a 128 MiB decoder memory limit. This leaves room for normal dictionaries, including the 64 MiB dictionary used by LZMA preset 9, while rejecting oversized decoder requirements before allocating the dictionary.

Zstandard decoding limits the frame window to 64 MiB. This is a window bound, not a total process memory limit; decoder buffers and the bounded input/output require additional memory. The limit exceeds the allowed control archive output to accommodate normal compressor settings. The supported python-zstandard native backends pass `max_window_size` to libzstd in bytes, despite the API documentation describing KiB. Regression tests exercise real frame windows at and above a small bound to check the effective units.

These checks apply during publication and dry-run. Decoder failures produce a contextual package error and prevent upload. Concatenated XZ/LZMA streams share the same output limit and each decoder receives the memory limit. Valid XZ padding is accepted; truncated streams, invalid padding, and non-stream trailing bytes are rejected. Packages requiring larger dictionaries or windows must have their control archive recompressed with smaller settings.

## NPM credential isolation

NPM publication requires npm 11.0.0 or newer in every mode, including `--allow-pack-scripts`, and uses two phases:

1. `npm pack --ignore-scripts` runs in the package directory before any Forgejo authentication file is created. Pack lifecycle scripts (`prepack`, `prepare`, and `postpack`) are disabled by default through an explicit command-line option.
2. `npm publish` runs from the temporary directory against the packed `.tgz`, receives a temporary `.npmrc`, forces `--registry` and `--strict-ssl=true`, and uses `--ignore-scripts`. The `.npmrc` contains the literal reference `${FORGE_PUBLISH_NPM_AUTH_TOKEN}` in the authentication entry scoped to the intended registry; it never contains the token value. Only a separate copy of the environment passed to this authenticated subprocess receives that variable's value. The token is not placed in command arguments or forge-publish messages, and the parent process environment is unchanged.

Before `npm --version` and `npm pack`, forge-publish removes `FORGE_PUBLISH_TOKEN`, `FORGE_PUBLISH_NPM_AUTH_TOKEN`, `NPM_TOKEN`, `NODE_AUTH_TOKEN`, and all inherited `npm_config_*` variables from the subprocess environment, without regard to case. Inherited variants of the dedicated publication variable are also removed before its canonical name is set for publish. Normal network and trust variables such as `HTTPS_PROXY`, `NO_PROXY`, and `NODE_EXTRA_CA_CERTS` remain available. `FORGE_PUBLISH_NPM_AUTH_TOKEN` is an internal subprocess variable, not an alternative way to configure a Forgejo token.

Avoiding plaintext temporary storage does not isolate credentials from processes running under the same account. Depending on operating-system permissions, those processes may inspect the parent process's memory or the authenticated npm process's environment and memory. Use a trusted account and npm installation; forge-publish does not provide a process sandbox. npm handles the token in memory, and its own output/cache/debug logs remain part of that trust boundary. The integration checks inspect npm output and debug logs on both successful and rejected authenticated publications.

`--allow-pack-scripts` explicitly re-enables only pack hooks with `--ignore-scripts=false`. Use it only for trusted packages. Hooks execute arbitrary same-user package code with other inherited environment variables; they can start background processes that outlive packing and access publication credentials through same-account process inspection. Removing tokens from the synchronous pack environment and keeping the temporary `.npmrc` token-free do not prevent that path. This option forfeits the strong credential-isolation guarantee against package lifecycle code; forge-publish does not sandbox hooks or their descendants. The authenticated publish still uses `--ignore-scripts` in every mode. Build generated files separately before publishing when pack hooks are unnecessary.

The `npm_config_*` rejection is intentionally blanket and case-insensitive. forge-publish does not maintain an allowlist for npm configuration variables, because inherited npm configuration can affect publication-sensitive behavior and standard environment variables already cover the required network/trust cases without weakening registry, credential, or TLS isolation. This means npm-style proxy, CA, retry, timeout, or cache variables are stripped when expressed as `npm_config_*`; use standard variables such as `HTTPS_PROXY`, `NO_PROXY`, and `NODE_EXTRA_CA_CERTS` instead.

Running the authenticated publish outside the package directory prevents a project-local `.npmrc` from overriding the temporary Forgejo credentials or TLS policy. Requiring npm 11.0.0 or newer ensures `--ignore-scripts` disables `prepare` during packing and command-line publication settings take precedence over conflicting `publishConfig` values. npm 10.x can execute `prepare` even with `--ignore-scripts` and is rejected before packing or creating authentication files. Prereleases of the minimum 11.0.0 release, such as `11.0.0-rc.0`, are rejected, while prereleases of later versions, such as `11.0.1-beta.1`, satisfy the implemented version check. The temporary archive and authentication file are removed automatically.
