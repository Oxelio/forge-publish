# Configuration

Run:

```bash
forge-publish config
```

or configure non-interactively:

```bash
forge-publish config \
    --url https://forge.example.com \
    --owner Software \
    --username my-user
```

The configuration contains the Forgejo URL, package owner, and username. The access token is never written to the TOML file.

## Configuration file location

`forge-publish` uses the operating system's native user configuration directory through `platformdirs`.

Typical locations are:

- Linux: `~/.config/forge-publish/config.toml`
- macOS: `~/Library/Application Support/forge-publish/config.toml`
- Windows: `%LOCALAPPDATA%\forge-publish\config.toml`

On Linux, `XDG_CONFIG_HOME` is respected.

## Token sources

The token lookup order is:

1. `FORGE_PUBLISH_TOKEN`
2. operating-system keyring
3. interactive prompt

For local interactive use, prefer the keyring. For CI/CD, use the environment variable through the CI platform's secret store.

## Example

```toml
url = "https://forge.example.com"
owner = "Software"
username = "my-user"
```

The token is deliberately absent.

## URL requirements

The Forgejo URL must:

- use HTTPS
- contain a hostname
- not contain embedded credentials
- not contain a query string or fragment
- not contain whitespace
- use a valid port when a port is specified

Use the canonical HTTPS URL of your Forgejo instance, including its base path if
it is hosted under a subpath. Generic and Debian uploads and package deletions
reject HTTP redirects rather than following them. A redirect to a login page or
another host cannot count as a successful publication or receive a redirected
package upload. If you receive an HTTP 3xx error, check the configured URL and
ensure that your reverse proxy accepts token authentication for the package API
without redirecting to an interactive login page.
