# Release process

Releases use Python Semantic Release and Conventional Commits.

The project has a single version source: `project.version` in `pyproject.toml`.

Python Semantic Release updates that value. At runtime, `forge_publish.__version__` reads the installed package metadata through `importlib.metadata`, so no second version constant has to be maintained.

Tags use the format `v{version}`.

`forge-publish` no longer permits zero-major releases: `allow_zero_version` is disabled. The transition from the existing `0.1.0` release to the stable public contract is deliberately guarded so an unrelated push cannot become `1.0.0`.

## Automatic release

A push to `main` runs `.github/workflows/release.yml`.

While the checked-out project version is still `0.x`, the workflow refuses to create a release unless a major release is explicitly requested. The normal 1.0 readiness merge uses the commit marker `[release:major]`; a manual workflow dispatch can instead select `release_level=major`. In either case the workflow calls `semantic-release version --major`, making the transition to `1.0.0` explicit rather than deriving it from an unrelated commit.

After the repository is at `1.0.0` or newer, normal pushes return to standard Conventional Commit version calculation. The explicit major override remains available for a deliberately requested future major release.

The workflow:

1. evaluates Conventional Commits
2. determines the next semantic version
3. updates `project.version` in `pyproject.toml`
4. updates `CHANGELOG.md`
5. builds the wheel and source distribution
6. creates the release commit and tag
7. creates the GitHub Release
8. generates `SHA256SUMS` for the built wheel and source distribution
9. signs build provenance attestations for those digests using GitHub OIDC
10. verifies the checksums again and uploads the distributions and manifest

The artifacts are built once by `semantic-release version`; `semantic-release
publish` uploads those same files without rebuilding them. Only wheels, source
distributions and `SHA256SUMS` are selected for upload. Checksum generation,
attestation and upload run only when Semantic Release reports a new release;
a no-release run skips all three. An attestation or checksum failure prevents
artifact upload, although the release commit, tag and GitHub Release may already
exist. Review the failed run before attempting recovery; do not substitute
rebuilt artifacts for the attested bytes.

Release tooling is declared in the `release` optional dependency group in `pyproject.toml`. The release workflow pins pip and installs `.[release]` using `requirements/tooling.txt`, while isolated package builds use `requirements/build.txt`. This keeps the release environment and build backend deterministic without turning forge-publish's normal runtime dependency ranges into exact user-facing pins.

Dependency updates are made through dedicated pull requests. Dependabot monitors the pip ecosystem weekly, and the exact constraints are reviewed together with the full CI and real Forgejo integration before merging.

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

The release job's `GITHUB_TOKEN` has only `contents: read`, `id-token: write`
and `attestations: write`. It obtains a short-lived signing certificate via
OIDC and stores provenance in GitHub's attestation service. The separate App
token retains responsibility for release commits, tags and asset uploads;
it is not used for attestation signing. No long-lived signing key is added.

## Verify downloaded artifacts

For releases produced by this workflow, download the wheel, source distribution
and `SHA256SUMS` from the same GitHub Release into an empty directory. For example,
replace `vX.Y.Z` below with the intended release tag:

```bash
gh release download vX.Y.Z --repo Oxelio/forge-publish \
    --pattern '*.whl' --pattern '*.tar.gz' --pattern SHA256SUMS
sha256sum --check SHA256SUMS
```

The manifest uses the standard GNU SHA-256 checksum format with artifact
basenames, so verification works from the download directory. On macOS,
`shasum -a 256 --check SHA256SUMS` is an alternative. Older releases do not
retroactively gain checksums or attestations.

Checksums detect changed bytes; verify the signed provenance as well to establish
which repository and workflow produced them. With an authenticated, current
GitHub CLI that supports artifact attestations:

```bash
for artifact in *.whl *.tar.gz; do
    gh attestation verify "$artifact" --repo Oxelio/forge-publish \
        --signer-workflow Oxelio/forge-publish/.github/workflows/release.yml
done
```

Inspect the verification output for the expected source commit and workflow.
The attestation identifies the triggering workflow commit; Semantic Release
bumps the project version and builds within that run before creating its release
commit and tag. Attestations are available through GitHub's repository
attestation service and the workflow summary, rather than as additional release
assets. They prove origin and integrity, not that an artifact is free of defects.

## Local verification

Preview the next release:

```bash
semantic-release -v --noop version
```

After a local distribution build, exercise checksum generation without signing
or publishing anything:

```bash
bash .github/scripts/release-checksums.sh
```

The Linux release-script regression tests cover both distribution digests,
repeatable output, missing distributions, upload selection and detection of
modified bytes. PR CI does not publish releases or request release attestations;
OIDC signing and remote attachment must also be verified on a release workflow
run by downloading its assets and executing the consumer commands above.

Create all local release changes without a commit or tag:

```bash
semantic-release -vv version --no-commit --no-tag
```

Do not run the full release command against `main` until the ruleset bypass is configured.
