# Release process

Releases use Python Semantic Release and Conventional Commits.

The current configuration tracks the version in:

- `pyproject.toml`
- `src/forge_publish/__init__.py`

Tags use the format `v{version}`.

While the project remains below 1.0, zero-major releases are enabled and breaking changes keep the project in the `0.x` line. Change `major_on_zero` when the project is ready for 1.0.

## Automatic release

A push to `main` runs `.github/workflows/release.yml`.

The workflow:

1. evaluates Conventional Commits
2. determines the next semantic version
3. updates version files
4. updates `CHANGELOG.md`
5. builds the wheel and source distribution
6. creates the release commit and tag
7. creates the GitHub Release
8. uploads the distribution artifacts

Python Semantic Release is pinned to version 10.6.2 in the project and workflow.

## Branch ruleset prerequisite

The repository currently requires changes to `main` to arrive through pull requests. Python Semantic Release normally creates and pushes a release commit directly.

Before enabling unattended releases, configure a dedicated GitHub App or release actor in the ruleset bypass list with permission to perform the release push. Keep normal contributors subject to the pull-request requirement.

The workflow uses `GITHUB_TOKEN`; if a different release actor is chosen, update the workflow to mint or provide that actor's token rather than weakening the ruleset globally.

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
