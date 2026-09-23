# Release process

Releases use Python Semantic Release and Conventional Commits.

The project has a single version source: `project.version` in `pyproject.toml`.

Python Semantic Release updates that value. At runtime, `forge_publish.__version__` reads the installed package metadata through `importlib.metadata`, so no second version constant has to be maintained.

Tags use the format `v{version}`.

While the project remains below 1.0, zero-major releases are enabled and breaking changes keep the project in the `0.x` line. Change `major_on_zero` when the project is ready for 1.0.

## Automatic release

A push to `main` runs `.github/workflows/release.yml`.

The workflow:

1. evaluates Conventional Commits
2. determines the next semantic version
3. updates `project.version` in `pyproject.toml`
4. updates `CHANGELOG.md`
5. builds the wheel and source distribution
6. creates the release commit and tag
7. creates the GitHub Release
8. uploads the distribution artifacts

Release tooling is declared once in the `release` optional dependency group in `pyproject.toml`. The workflow installs `.[release]`, so Python Semantic Release and build-tool versions are not duplicated in workflow YAML.

## GitHub App and branch ruleset

Automatic releases use a dedicated GitHub App rather than a long-lived personal access token.

Create a GitHub App for releases with repository access limited to this repository and grant it:

- **Contents: Read and write**
- **Metadata: Read-only** (automatic)

The release process does not need **Workflows: Write** because the generated release commit only updates release metadata such as `pyproject.toml` and `CHANGELOG.md`. If release automation is later changed to modify files under `.github/workflows/`, review the App permissions before doing so.

Install the App on `forge-publish`, then configure:

- repository variable `RELEASE_APP_CLIENT_ID` with the App client ID
- repository secret `RELEASE_APP_PRIVATE_KEY` with a generated private key for the App

The workflow uses `actions/create-github-app-token` to mint a short-lived installation token for each release run. Release workflow Actions are pinned to full commit SHAs rather than mutable tags.

The repository ruleset currently requires pull requests and the `Quality checks` status check on `main`. Add the release GitHub App to the ruleset **Bypass list** with **Always allow**. Do not use **For pull requests only**, because Python Semantic Release must push its generated release commit and tag directly.

Keep normal users subject to the existing ruleset.

## Local verification

Preview the next release:

```bash
semantic-release -v --noop version
```

Create all local release changes without a commit or tag:

```bash
semantic-release -vv version --no-commit --no-tag
```

Do not run the full release command against `main` until the ruleset bypass is configured.
