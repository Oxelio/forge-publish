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
8. installs the built wheel with constrained runtime dependencies in a clean environment and generates/validates `forge-publish.cdx.json`
9. generates `SHA256SUMS` for both distributions and the SBOM
10. signs build provenance attestations for those digests using GitHub OIDC
11. verifies the checksums again and uploads the distributions, SBOM and manifest
12. retrieves that release's assets in a separate `pypi` job, checks every
    checksum, and uploads only the unchanged wheel and sdist to PyPI using OIDC
13. installs the package actually served by PyPI with pipx in a clean environment,
    compares its wheel with the GitHub asset and verifies both CLI entry points

The artifacts are built once by `semantic-release version`; `semantic-release
publish` uploads those same files without rebuilding them. Only wheels, source
distributions, `forge-publish.cdx.json` and `SHA256SUMS` are selected for upload.
SBOM/checksum generation, attestation and upload run only when Semantic Release
reports a new release; a no-release run skips them. An SBOM, attestation or
checksum failure prevents artifact upload, although the release commit, tag and GitHub Release may already
exist. Review the failed run before attempting recovery; do not substitute
rebuilt artifacts for the attested bytes.

Release tooling is declared in the `release` optional dependency group in `pyproject.toml`. The release workflow pins pip and installs `.[release]` using `requirements/tooling.txt`, while isolated package builds use `requirements/build.txt`. This keeps the release environment and build backend deterministic without turning forge-publish's normal runtime dependency ranges into exact user-facing pins.

Dependency updates are made through dedicated pull requests. Dependabot monitors the pip ecosystem weekly, and the exact constraints are reviewed together with the full CI and real Forgejo integration before merging.

## PyPI distribution

PyPI is the primary end-user channel, with `pipx install forge-publish` as the
recommended installation. GitHub Releases remain authoritative for release
notes, SHA256SUMS, SBOMs and GitHub provenance. The first PyPI publication must
exercise the normal post-merge release workflow and live validation described
below; existing GitHub-only releases must not be manually backfilled.

Before enabling this workflow on `main`, a maintainer must configure:

- a GitHub Environment named **`pypi`**, restricted to deployment from **`main`**;
- a PyPI Trusted Publisher for project **`forge-publish`**, GitHub owner
  **`Oxelio`**, repository **`forge-publish`**, workflow **`release.yml`**,
  environment **`pypi`**.

If the project does not exist yet, add a
[Pending Trusted Publisher](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)
from the maintainer's PyPI account. Verify that PyPI accepts this project name;
an anonymous 404 does not establish registrability or ownership. A pending
publisher does not reserve the name, so verify it again before the first upload.
If it belongs to another account or cannot be registered, stop and obtain a
maintainer decision; do not substitute another distribution name.

No PyPI token/password repository secret is needed. The publishing job alone
gets `id-token: write` for PyPI, independently of the existing release job's
OIDC permission for GitHub attestations. It has read-only repository contents,
uses the pinned [PyPA publishing action](https://github.com/pypa/gh-action-pypi-publish),
and does not install or build this package. Checkout credentials are not
persisted. The subsequent installation smoke job has no OIDC or write access.

The release job exposes only its new-release flag and exact tag. A successful
new release on `main` is required before the PyPI job runs, including manual
dispatches; no-release runs and dispatches on other branches cannot publish.
The job downloads that tag's wheel, sdist, SBOM and SHA256SUMS. The validator
requires exactly those files and one correct checksum per artifact, checks the
versioned filenames against the tag, and stages only the two distributions.
It fails before upload on extra/missing files or any checksum error. Neither
job rebuilds the package or uploads the SBOM/checksum manifest to PyPI.

The separate smoke job waits for the uploaded version to become visible with
a bounded retry, downloads its wheel from PyPI and compares the actual bytes
with GitHub. It then runs the documented `pipx install forge-publish`, verifies
the installed version matches the new release, exercises `--version`, `--help`
and `python -m forge_publish --help`, runs `pip check`, and uninstalls the CLI.
This validation needs a real PyPI publication; local wheel/sdist checks alone
cannot satisfy it. The first normal release after merge must exercise this
permanent workflow before issue #45 can be closed.

A failed upload or smoke test does not undo the GitHub Release or files already
published on PyPI. Inspect the failed run and PyPI state before recovery. The
action deliberately does not skip existing files; preserve the exact validated
bytes, never rebuild or silently overwrite a version. A retry that produces
no new semantic release skips publication rather than backfilling an old tag.

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

Normal pull requests are squash-merged, with merge commits and rebase merging
disabled in both repository settings and the `main` ruleset. The default squash
message uses the PR title and description. Conventional Commit PR titles with
GitHub's PR number suffix become the squash titles used for version calculation.
GitHub deletes merged topic branches automatically.
Keep the existing required `Quality checks` check and strict up-to-date policy
when maintaining these settings. See the
[contributor merge policy](development.md#pull-requests-and-merge-policy).

The release App's **Always allow** bypass remains an exception for its generated
release commits and tags. Restricting normal PR merge methods must preserve that
bypass and its existing permissions; no additional bypass actor is needed.

The release job's `GITHUB_TOKEN` has only `contents: read`, `id-token: write`
and `attestations: write`. It obtains a short-lived signing certificate via
OIDC and stores provenance in GitHub's attestation service. The separate App
token retains responsibility for release commits, tags and asset uploads;
it is not used for attestation signing. No long-lived signing key is added.

## Verify downloaded artifacts

For releases produced by this workflow, download the wheel, source distribution,
the SBOM and `SHA256SUMS` from the same GitHub Release into an empty directory. For example,
replace `vX.Y.Z` below with the intended release tag:

```bash
gh release download vX.Y.Z --repo Oxelio/forge-publish \
    --pattern '*.whl' --pattern '*.tar.gz' --pattern forge-publish.cdx.json --pattern SHA256SUMS
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
for artifact in *.whl *.tar.gz forge-publish.cdx.json; do
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

## Release SBOM

Each new release includes one `forge-publish.cdx.json` document in
[CycloneDX 1.6 JSON](https://cyclonedx.org/docs/1.6/json/). The pinned
[CycloneDX Python CLI](https://cyclonedx-bom-tool.readthedocs.io/en/latest/usage.html)
generates it from the actual built wheel installed with `requirements/tooling.txt`
in a separate runtime environment. The release job uses Linux/Python 3.14 and
installs no dev/release extras there. The generator itself runs in the tooling
environment, not in the environment being inventoried.

The root identity and runtime requirements come from the wheel's metadata after
the version bump. Project, wheel, sdist and installed metadata must agree before
generation. The document keeps the reachable runtime dependency graph, excluding
unrelated bootstrap tools such as pip, and records exact resolved component
versions, package URLs and available declared license metadata. Tool identities
remain under `metadata.tools`, separate from application dependencies. References
to both release distributions include their SHA-256 hashes. The document is
schema-validated both before and after these additions; any validation failure
stops publication. Repeated generation for the same artifacts, dependency
environment and tooling produces the same bytes, without random IDs/timestamps.

This is a **reference runtime profile**, not a list of vendored libraries or a
universal dependency lock. Wheel/sdist dependencies retain compatible ranges;
end users may resolve other versions. Windows, other Python versions, selected
extras, native libraries, Python itself, Node/npm and Forgejo are not inventoried
by this Linux base-runtime profile. The sdist reference identifies the matching
project source, not every tool that an end user might use to build it. Inspect
`metadata.properties` for the profile and resolution policy. Runtime requirement
ranges remain authoritative in the distribution's `Requires-Dist` metadata.

Download the document alongside the wheel/sdist and verify `SHA256SUMS` and its
build provenance as above. Read the JSON with a CycloneDX-compatible consumer,
or inspect `metadata.component`, `components` and `dependencies` directly.
With the constrained release tooling installed, validate a downloaded document:

```bash
python - <<'PY'
from pathlib import Path
from cyclonedx.schema import SchemaVersion
from cyclonedx.validation.json import JsonStrictValidator

data = Path("forge-publish.cdx.json").read_text(encoding="utf-8")
error = JsonStrictValidator(SchemaVersion.V1_6).validate_str(data)
if error is not None:
    raise SystemExit(str(error))
print("Valid CycloneDX 1.6 document")
PY
```

The existing OIDC provenance step also attests the SBOM's bytes, with no new
permissions or signing credential. A separate CycloneDX **SBOM predicate
attestation** is deliberately deferred: the single release document already
identifies both distributions by hash, and publishing another attestation is
unnecessary for this initial consumer contract. Provenance of the SBOM is not a
claim that every consumer's eventual dependency resolution matches this profile.
Older releases do not retroactively gain an SBOM.

PR CI reuses its clean wheel smoke-test environment to exercise generation and
checksums without rerunning tests or installing a second runtime profile. For
local generation after `python -m build`, install the built wheel into a fresh
virtual environment with the runtime constraints (no extras), run `pip check`,
then invoke the script from the constrained development/release environment:

```bash
python .github/scripts/release-sbom.py --python /path/to/runtime-venv/bin/python
bash .github/scripts/release-checksums.sh
```

On Windows pass the environment's `Scripts/python.exe` instead. Generator tests
cover release-version mismatches, runtime requirements, graph completeness,
schema failures, stable output, artifact hash references and private/local URL
rejection. The release workflow must still confirm actual remote asset upload
and OIDC provenance after the PR is merged.

## Local verification

Preview the next release:

```bash
semantic-release -v --noop version
```

After a local distribution build and SBOM generation, exercise checksums without signing
or publishing anything:

```bash
bash .github/scripts/release-checksums.sh
```

The Linux release-script regression tests cover distribution/SBOM digests,
repeatable output, missing distributions, upload selection and detection of
modified bytes. PR CI does not publish releases or request release attestations;
OIDC signing and remote attachment must also be verified on a release workflow
run by downloading its assets and executing the consumer commands above.

Create all local release changes without a commit or tag:

```bash
semantic-release -vv version --no-commit --no-tag
```

Do not run the full release command against `main` until the ruleset bypass is configured.
