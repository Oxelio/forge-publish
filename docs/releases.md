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

Python Semantic Release is pinned to version 10.6.2 in the project and workflow.

## Branch ruleset prerequisite

The repository currently requires changes to `main` to arrive through pull requests. Python Semantic Release normally creates and pushes a release commit directly.

Before enabling unattended releases, configure a dedicated GitHub App or release actor in the ruleset bypass list with permission to perform the release push. Keep normal contributors subject to the pull-request requirement.

The workflow uses the `RELEASE_TOKEN` repository secret when it is configured and falls back to `GITHUB_TOKEN` otherwise. For the current protected `main` branch, configure `RELEASE_TOKEN` with a token belonging to a dedicated release actor that is allowed to bypass the pull-request rule. Do not weaken the ruleset globally.

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
