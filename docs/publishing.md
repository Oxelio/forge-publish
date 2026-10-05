# Publishing packages

## Debian

```bash
forge-publish deb package.deb \
    --distribution bookworm \
    --component main
```

Short forms are available:

```bash
forge-publish deb package.deb -d bookworm -c main
```

`forge-publish` reads the Debian control metadata directly and does not require `dpkg-deb` for publication.

Supported control archive formats:

- `control.tar`
- `control.tar.gz`
- `control.tar.xz`
- `control.tar.zst`
- `control.tar.bz2`
- `control.tar.lzma`

The target endpoint is:

```text
PUT /api/packages/{owner}/debian/pool/{distribution}/{component}/upload
```

## Generic

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 2.4.0
```

The source filename is used by default. Override it with:

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 2.4.0 \
    --filename firmware-linux.bin
```

The target endpoint is:

```text
PUT /api/packages/{owner}/generic/{package}/{version}/{filename}
```

## NPM

Publish the current directory:

```bash
forge-publish npm
```

or another directory:

```bash
forge-publish npm ./my-package
```

The package must contain a valid `package.json` with a name and version. NPM publishing requires npm 10.5.2 or newer so command-line publication settings reliably take precedence over `publishConfig` values embedded in the package. Prereleases of the minimum 10.5.2 release are not supported: for example, `10.5.2-rc.0` is rejected. A prerelease of a later version, such as `10.5.3-beta.1`, is accepted because it is newer than the minimum supported version.

Pack lifecycle scripts (`prepack`, `prepare`, and `postpack`) are disabled by default with an explicit `npm pack --ignore-scripts`, even if npm configuration enables them. Packages that generate files in these hooks must build those files before publication, or explicitly enable the hooks for a trusted package:

```bash
forge-publish npm ./my-package --allow-pack-scripts
```

This option passes `--ignore-scripts=false` only to the pack phase, overriding npm configuration that disables scripts. It executes package code with other inherited environment variables. A hook can leave background processes running that may read the Forgejo credentials introduced later; opt-in therefore forfeits that credential-isolation guarantee. The CLI displays a warning and the selected policy, including during `--dry-run`. Authenticated publication always keeps lifecycle scripts disabled. See [NPM credential isolation](security.md#npm-credential-isolation).

The package is first packed without Forgejo credentials. The generated archive is then published from an isolated temporary directory with a temporary authentication file, TLS verification forced on, lifecycle scripts disabled, and inherited `npm_config_*` settings removed. Project-local `.npmrc`, environment-level npm configuration, and conflicting `publishConfig.registry` or `publishConfig.strict-ssl` values therefore cannot redirect the authenticated publish or disable TLS verification.

Inherited `npm_config_*` variables are intentionally rejected case-insensitively rather than selectively allowlisted, including proxy, custom-CA, retry, timeout, and cache settings expressed through npm configuration. For supported network or trust customization, use standard environment variables such as `HTTPS_PROXY`, `NO_PROXY`, and `NODE_EXTRA_CA_CERTS`; these remain available to npm. This keeps the registry, authentication file, TLS verification, and authenticated publish behavior deterministic.

## Dry-run

Every publisher supports `--dry-run`.

Examples:

```bash
forge-publish generic firmware.bin \
    --package firmware \
    --version 2.4.0 \
    --dry-run

forge-publish deb package.deb \
    --distribution bookworm \
    --component main \
    --dry-run

forge-publish npm --dry-run
```

Dry-run validates local metadata and displays the operation without requiring a Forgejo token.

## Insecure TLS

Debian and Generic publication support `--insecure` for controlled environments using certificates that cannot be validated by the local trust store.

Prefer installing the correct CA certificate instead. NPM publication does not expose an insecure-TLS option.
