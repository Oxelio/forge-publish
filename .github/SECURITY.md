# Security policy

This policy covers vulnerability reporting and security support for
`forge-publish`. For details about credential handling, TLS and other security
behavior, see [Security](../docs/security.md).

## Supported versions

Security fixes target the latest available release in the current major series,
currently **2.x**.

| Version | Security support |
| --- | --- |
| Latest available 2.x release | Supported |
| Older 2.x releases | Upgrade to the latest 2.x release |
| 1.x and earlier | Unsupported |

Fixes are not routinely backported to older minor or patch releases. When a new
major becomes current, support moves to that major unless the maintainer
explicitly announces support for an older major in parallel. Check
[GitHub Releases](https://github.com/Oxelio/forge-publish/releases/latest) for the
latest release.

## Report a vulnerability privately

Use [GitHub Private Vulnerability Reporting](https://github.com/Oxelio/forge-publish/security/advisories/new).
Sign in to GitHub, or open the repository's **Security > Advisories** page and
select **Report a vulnerability**. Reports are shared privately with the
repository maintainers.

Do not open a public issue containing sensitive or exploitable details. Keep
reproduction material and any proof of concept private until disclosure has been
coordinated with the maintainers. Do not include real credentials, personal data
or unrelated confidential information; use redacted logs and harmless fixtures.

A useful report includes:

- The affected forge-publish version and installation method.
- The operating system, Python version and relevant npm or Forgejo versions.
- The affected command or scenario, required conditions and configuration.
- Expected and observed behavior, practical impact and affected assets.
- Reproduction steps and a minimal proof of concept or sample package when useful.
- Relevant redacted logs or error messages and any known workaround.

Report suspected vulnerabilities even if you are unsure about the impact.

## Communication and disclosure

Maintainers handle reports on a **best-effort** basis and use the private GitHub
report to discuss impact, request missing details, and coordinate remediation and
disclosure with the reporter. Response and remediation times depend on severity,
complexity and maintainer availability; no fixed response or remediation deadline
is promised.

When a fix is available, maintainers coordinate publication of a security
advisory and upgrade guidance as appropriate. Users should upgrade to the latest
release in the supported major series.
