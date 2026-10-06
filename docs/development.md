# Development

## Setup

Python 3.11 through 3.14 are supported.

Use an editable installation only when developing from a source checkout.
For normal CLI use, follow the [end-user installation](../README.md#installation).
Activate the virtual environment before installing the source package:

```bash
python -m venv .venv
# Activate .venv using your shell's activation command.
python -m pip install "pip==26.2.1"
python -m pip install \
    --constraint requirements/tooling.txt \
    --build-constraint requirements/build.txt \
    -e ".[dev,release]"
```

Activate the virtual environment using the normal command for your shell.

## Tests

```bash
pytest
```

Coverage and branch coverage are enabled through `pyproject.toml`, with an enforced minimum of 85%.

Generate an HTML report with:

```bash
pytest --cov-report=html
```

### Debian parser fuzz corpus

`tests/test_deb_fuzz.py` runs in the normal pytest suite on every supported CI
platform. It uses Python's standard-library `random.Random(47)` and explicit
iteration/input limits rather than adding Hypothesis or a scheduled heavyweight
fuzzer. This keeps the initial strategy reproducible and dependency-free while
covering arbitrary bytes, ar headers, truncations, mutated tar archives and
generated control fields across all six supported compression formats. Valid
inputs must return the expected metadata; arbitrary/mutated inputs may return
metadata or raise `PackageError`, but must not leak unexpected exceptions.

Run the corpus locally with:

```bash
pytest tests/test_deb_fuzz.py --no-cov
```

Inputs are at most 32 KiB and exist only in memory. Tests lower parser resource
limits, check bounded ar reads and rejection before oversized payload reads,
exercise exact decompressed/control-file boundaries, and retain decoder-memory
and malformed GNU/PAX extension seeds from the existing regression suite.
Huge declared sizes are header-only fixtures, never huge allocated payloads.
Filesystem extraction APIs are forbidden. There are no timing assertions;
bounded inputs/iterations and the existing CI job timeouts limit test execution
without introducing timing-dependent failures. This corpus is a regression
guard, not an exhaustive proof of parser safety or a sandbox for native crashes.

Failures report the seed and case (format, corpus index, mutation/truncation
index) in the exception notes. Re-run the same test to reproduce. If a mutation
discovers a defect, minimize it into a named fixture and explicit regression
test in `tests/test_deb.py`, then add that fixture to the fuzz seeds. Keep seeds
and iteration budgets explicit and reviewable when extending the corpus.

## Linting and formatting

```bash
ruff check .
ruff format --check .
```

Apply automatic fixes with:

```bash
ruff check . --fix
ruff format .
```

## Static type checking

After installing the Python dependencies above, activate that virtual environment
so `python` selects its interpreter. Install Node.js 24.21.0 and npm 11.0.0 (the
same versions used by the dedicated CI job), then bootstrap the locked checker:

```bash
npm install --global npm@11.0.0 --ignore-scripts
npm ci --prefix .github/typecheck --ignore-scripts
```

Run the same command locally and in CI, from the repository root:

```bash
python .github/scripts/typecheck.py
```

The script invokes the locally installed
[official npm distribution of Pyright](https://github.com/microsoft/pyright/blob/main/docs/installation.md)
with the repository's `[tool.pyright]` configuration and `sys.executable`, so it
uses the same interpreter and installed dependencies as the command above. It
fails if Node or the installed checker is missing, without downloading a fallback.
The checker's exact version and package integrity hashes are committed in
`.github/typecheck/package-lock.json`; `npm ci` refuses lockfile drift. This avoids
the Python wrapper's separate Node/checker download bootstrap. Node is needed
only for this check and the existing NPM integration, not the Python test matrix
or the installed forge-publish CLI. Python tooling constraints are unchanged.

The initial `basic` baseline includes every production module under `src` and
targets Python 3.11, the oldest supported runtime. It deliberately does not
include `tests` or `.github/scripts`: their fixture/mocking conventions and
automation code can be adopted separately. Ruff and pytest continue to cover
them. No diagnostic is disabled and no broad ignore hides source errors;
warnings also cause the command to fail. The runtime matrix continues testing
Python 3.11–3.14 on Linux and Windows.

For progressive adoption, enable `# pyright: strict` in an individual module once
it has a clean strict baseline, or add test/script directories with their own
explicit execution environments. Review surfaced errors before increasing the
global mode. Pyright complements runtime tests; this initial baseline does not
promise complete third-party typing or global strictness.

To upgrade Pyright, update the exact version in `.github/typecheck/package.json`,
regenerate its lock with npm 11.0.0, and run `npm ci` plus the check above. Review
new diagnostics and the dependency diff. Dependabot proposes weekly updates for
this isolated npm tooling directory.

## Pre-commit

Install hooks:

```bash
pre-commit install
pre-commit install --hook-type commit-msg
```

The repository uses Conventional Commits.

Examples:

```text
feat(cli): add a command
fix(config): reject an invalid value
docs: clarify package publishing
test(client): cover an HTTP error
chore(ci): update the Python matrix
```

## Pull requests and merge policy

`main` is the only permanent branch. Create a topic branch for each change and
open a pull request targeting `main`. Normal pull requests use **Squash and
merge** only; repository settings and the `main` ruleset exclude merge commits
and rebase merging. GitHub automatically deletes merged topic branches.

Use a Conventional Commit title for the pull request: it becomes the squash
commit title and determines Semantic Release's version calculation. The default
squash message uses the PR title and description. Keep GitHub's PR number suffix
in the final squash title, for example `fix(cli): reject invalid input (#72)`.
Review the final message so intermediate working commits do not independently
influence the release.

Merge only after the required `Quality checks` gate succeeds on the current
head and the branch is up to date with `main`, as required by the ruleset.
Review comments and resolve requested changes before merging. The release App's
existing bypass is reserved for generated release commits and tags; normal
contributions follow the pull-request protections. See the
[release App and ruleset configuration](releases.md#github-app-and-branch-ruleset).

## CI

Pull requests run:

- Ruff linting
- Ruff formatting verification
- Pyright production-source checking with a locked checker and Python 3.11 baseline
- universal tooling-constraints regeneration and Ruff/Commitizen hook alignment
- unit tests with coverage
- dependency review for pull request dependency changes, blocking newly introduced high/critical known vulnerabilities
- wheel and sdist build verification
- Python 3.11, 3.12, and 3.13 compatibility jobs on Linux, including dev/release dependency resolution and `pip check`
- the full quality suite on Python 3.14
- Windows compatibility on Python 3.11 and 3.14, including dev/release dependency resolution and `pip check`

The repository ruleset continues to require the `Quality checks` status. CI runs Dependency Review, the main quality suite, Pyright, Forgejo integration, the Linux compatibility matrix, and the Windows compatibility matrix in parallel. A final job named `Quality checks` depends on all six groups and fails unless every group succeeds.

Dependency Review evaluates only dependency changes introduced by the pull request and fails for newly introduced known vulnerabilities with high or critical severity. It uses read-only repository contents permission and reports findings through the GitHub Actions check output. License enforcement is explicitly disabled until the project defines a dependency-license policy. Dependabot remains enabled for weekly GitHub Actions and Python dependency updates; it is complementary to this merge-time review rather than replaced by it.

The Forgejo integration workflow starts a digest-pinned Forgejo 16.0.5 image with an ephemeral self-signed TLS certificate and validates real Generic, Debian, and NPM publication through the CLI. Node.js is pinned to 24.21.0. NPM publication is exercised twice against the same Forgejo instance: once with the npm version bundled with that pinned Node.js runtime and once after explicitly installing and verifying the minimum supported npm 11.0.0. The two publications use distinct package versions so both compatibility paths are validated without hard-coding an assumed bundled npm version. The workflow also verifies that Forgejo rejects invalid credentials.

The container publishes its HTTPS port only on the runner's IPv4 loopback
(`127.0.0.1:3000:3000`). Its non-admin integration user receives only
`write:package`, the [Forgejo package scope](https://forgejo.org/docs/v16.0/user/authentication/token-scope/)
needed for Generic, Debian, and NPM publication; no repository, user, or admin
scope is granted. A separate `read:package` token must fail to upload, checking
the required write permission against the pinned server rather than assuming
`all` is necessary.

Readiness curl trusts the generated certificate with `--cacert`. Generic and
Debian publication, plus invalid/read-only authentication checks, use
`REQUESTS_CA_BUNDLE` and normal certificate verification. The workflow first
requires a TLS verification failure without that trust, then separately
publishes one Generic fixture using explicit `--insecure` to retain opt-in
coverage. NPM keeps its independent `NODE_EXTRA_CA_CERTS` trust path. These
checks reduce fixture exposure and privilege; running on a self-hosted runner
still requires Docker, the workflow's Linux tools, an available loopback port,
and isolation from unrelated jobs using the same Docker daemon.

### Forgejo compatibility and support

forge-publish supports explicitly validated Forgejo release lines that are still
maintained upstream. The current compatibility targets are **15.x LTS** at
**15.0.9** and **16.x stable** at **16.0.5**. Support requires a successful full
integration job for the pinned patch release; adding a matrix entry alone does
not establish compatibility. Inspect the version-labelled jobs in
[Forgejo compatibility runs](https://github.com/Oxelio/forge-publish/actions/workflows/compatibility.yml)
and the reference integration job in
[CI](https://github.com/Oxelio/forge-publish/actions/workflows/ci.yml) for evidence.
The fixture verifies the server's reported version before any publication.

[Forgejo's upstream releases](https://forgejo.org/releases/) list maintenance
status. At this policy's introduction, 15.x LTS is maintained until 15 July 2027
and 16.x stable until 29 October 2026. Upstream EOL ends our support even if an
older integration job passed. Unlisted or EOL releases may work, but carry no
support commitment. Supporting these server lines does not promise testing
every patch, server configuration, database backend or deployment topology.

Ordinary pull requests continue using only the 16.0.5 reference in the existing
`Quality checks` aggregate. The separate `compatibility.yml` workflow runs every
Monday at 05:23 UTC and can be started with **Run workflow**. It reuses
`integration.yml` for every matrix entry, covering Generic, Debian, both npm
versions, pack-script consent, authentication rejection and TLS verification.
It also runs on pull requests that change either integration workflow, so a
matrix update is validated before merge. `fail-fast: false` allows both versions
to report independently. Scheduled failures are visible per version and require
investigation; the compatibility workflow is not an additional required status
and does not retroactively block unrelated PRs. Repository protections remain
unchanged.

To update the supported set:

1. Check upstream maintenance status and release notes. Select an explicit patch
   release; new upstream majors are candidates until validated, not automatically
   supported.
2. Inspect its official image, for example
   `docker buildx imagetools inspect codeberg.org/forgejo/forgejo:15.0.9`, and review
   the digest and runner architecture. Add the version/digest pair to the closed
   image selection in `integration.yml`; never substitute a mutable `latest` tag.
3. Update the dispatch choices in `integration.yml` and the version matrix in
   `compatibility.yml`. When advancing the PR reference, update both input
   defaults in `integration.yml` as well.
4. Run the complete compatibility matrix on the update PR or manually on its
   branch. Inspect every version's job, including npm isolation and TLS/auth
   checks. Document a release line as supported only after its suite succeeds.
5. Update this policy and README. Keep previously validated, maintained lines
   until upstream EOL unless an earlier removal has an explicit documented
   decision. Remove EOL versions from the matrix and image selection; if the
   reference reaches EOL, move it to a newly validated maintained line too.

Unsupported reusable-workflow version inputs fail before starting a container.
The ordinary PR default remains pinned in the reusable workflow, so matrix
changes cannot silently change the required reference integration.

For NPM, both compatibility publications deliberately include conflicting project-local NPM authentication and TLS settings plus conflicting `publishConfig.registry` and `publishConfig.strict-ssl` values. Each publish must still use the temporary Forgejo credentials and verified TLS through Node's `NODE_EXTRA_CA_CERTS` mechanism.

The shared `tests/fixtures/npm_lifecycle` fixture records harmless pack-hook events and rejects credential environment variables or authenticated publish hooks. Both npm compatibility publications verify that no pack hook runs by default, even with project `ignore-scripts=false`. A third publication uses explicit `--allow-pack-scripts` consent with the minimum npm version and project `ignore-scripts=true`, verifying all three pack hooks and preserving script-free authenticated publication. The local pytest lifecycle tests execute real npm pack when supported npm is available, intercept the upload, and inspect the archive with fake tokens; these tests skip when npm is absent or unsupported, while Forgejo CI always provisions supported npm. Unit tests verify that unsupported npm is rejected in both modes before packing or creating authentication files.

NPM credential regression tests observe version detection, packing and publication
in both lifecycle modes, including failures. They check token-free temporary
files and arguments, case-insensitive removal of the dedicated publication
variable from preparation environments, a separate authenticated environment,
unchanged parent environment, output and cleanup. The Forgejo integration uses
`.github/scripts/npm-integration.py` to check successful publication with bundled
npm and npm 11.0.0, plus rejected npm authentication. It checks captured stdout,
stderr and npm debug logs for token values before displaying output. Rejected
authentication must fail at publication, not preparation or TLS validation.

Distribution verification installs both the built wheel and the built source distribution into separate clean virtual environments, runs `pip check`, and exercises the installed CLI from each artifact. The quality job reuses that runtime-only wheel environment to generate and schema-validate the release SBOM and verify its distribution/SBOM checksums. See [Release SBOM](releases.md#release-sbom) for its profile and consumer limitations. Release dependencies are validated with `pip check` as well.

The same quality job stages the generated release assets through the PyPI
checksum validator without uploading anything. Its regression tests reject
tampering, missing/duplicate manifest entries, path traversal, wrong versions
and unexpected assets. PyPI uploads and installation smoke tests run only after
a new GitHub Release succeeds; see [PyPI distribution](releases.md#pypi-distribution).

Development, CI, integration, and release environments use `requirements/tooling.txt` as an exact constraints set while `pyproject.toml` keeps compatible dependency ranges for normal forge-publish users. Isolated PEP 517 builds use the separate `requirements/build.txt` build constraint so the build backend is deterministic as well. pip itself is pinned in these controlled environments.

## SonarQube Cloud quality analysis

The integration is prepared for **SonarQube Cloud** with the built-in **Sonar
Way** Quality Gate. External project provisioning and successful baseline/PR
analysis must be confirmed before calling the rollout complete. Sonar is
initially a **non-required signal**: its analysis job waits for the gate and
reports failures, but is not a dependency of `Quality checks` or a separate
required repository check. Do not interpret missing setup or a failed analysis
as a passing Quality Gate.

### Maintainer setup

1. Import this public GitHub repository into the intended SonarQube Cloud
   organization. Copy the real organization key, project key and regional
   server URL from its CI setup instructions; do not infer them from the
   repository name. Confirm the Sonar GitHub integration can decorate PRs.
2. Disable Automatic Analysis and select CI-based analysis so Python XML
   coverage is imported. Select the built-in **Sonar Way** gate and confirm
   `main` is the project's main branch. Review its new-code definition before
   assessing the baseline.
3. Under GitHub **Settings > Secrets and variables > Actions**, create repository
   variables `SONAR_ORGANIZATION`, `SONAR_PROJECT_KEY` and `SONAR_HOST_URL` with
   the copied non-secret values. The URL must use HTTPS and identify the chosen
   Cloud region. Create repository secret `SONAR_TOKEN` with analysis permission
   for this project. Never put its value in source, an issue or a workflow log.
4. After the workflow is on `main`, run **SonarQube Cloud** manually from `main`
   or inspect its next non-release push run. Inspect **Sonar analysis and Quality
   Gate** in Actions and the linked Cloud project: verify the analyzed SHA,
   source/test classification, imported coverage, baseline findings and gate
   result. Generated `[skip ci]` release commits do not repeat the analysis.
5. Verify an internal PR produces analysis and PR decoration, imports its own
   coverage report and reports the actual Sonar Way result. Record this evidence
   in #30. Verify a fork PR skips the Sonar job without receiving the secret.

PR analysis reuses `coverage.xml` from CI's quality job through the
`sonar-coverage` artifact in the **same workflow run**. The dedicated main-branch
workflow produces that report with one constrained pytest run; it does not run
another PR test suite. Coverage uses repository-relative paths so the XML is
portable between runners. Analysis uses full Git history and the same checkout
SHA as the report. Artifacts expire after one day; rerunning an analysis after
expiry requires regenerating its coverage in that run. Local pytest, Ruff and
Pyright need no Sonar account, token or scanner.

Production sources are `src`, tests are `tests`, and supported Python versions
are 3.11–3.14. No source exclusions are added. The pytest 85% branch-aware global
threshold remains authoritative. Sonar Way provides complementary new-code
reliability, security, maintainability, hotspot-review, coverage and duplication
checks; do not add a duplicate global 85% gate in Sonar. Contributors can inspect
findings and the gate through the Sonar PR decoration/project link and the
Actions analysis logs. Triage baseline findings before tightening enforcement.

Forks, including dependency-bot PRs from external repositories, cannot enter
the secret-bearing Sonar call. This is an expected skip, not evidence of a
successful analysis. No `pull_request_target` or privileged `workflow_run`
consumes PR code or artifacts. Missing variables/token on an internal PR or
`main` cause an explicit setup failure in the non-required analysis job.

Once main/PR analysis, coverage import, decoration and useful gate results are
demonstrated, make a separate reviewed rollout change to include Sonar in
`Quality checks`. That change must distinguish the expected fork skip from an
analysis or gate failure, and retain the stable required check rather than
adding a separate long-term required Sonar check.

## CodeQL code scanning

GitHub manages the repository's CodeQL **default setup** outside the source tree.
It scans Python with the default high-precision query suite, the remote-sources
threat model and a standard GitHub-hosted runner. Scans run on pushes and pull
requests to `main` and protected branches, and on GitHub's weekly schedule.
There is no custom CodeQL workflow or local installation requirement.

Review results in [Security and quality > Code scanning](https://github.com/Oxelio/forge-publish/security/code-scanning)
and inspect the tool status there to confirm the analyzed commit, successful
upload and scan coverage. An empty alert list before a completed analysis is
not evidence of a clean baseline. Pull requests expose CodeQL check results
and annotations for findings introduced by their changes.

For each alert, inspect the rule, affected code and any source-to-sink paths.
Confirm reachability, existing validation and practical impact before deciding
whether it needs a fix. Track confirmed findings with reproduction details and
a regression test where practical. Dismiss a false positive or an accepted risk
only with a specific recorded reason; do not dismiss alerts merely to make a
check green. See GitHub's [alert assessment guidance](https://docs.github.com/en/code-security/how-tos/manage-security-alerts/manage-code-scanning-alerts/assess-alerts).

CodeQL is complementary to Ruff, pytest, Pyright, Dependency Review and any
future SonarQube quality analysis. The existing `Quality checks` aggregate
continues to govern the repository's CI gate; default-setup CodeQL checks are
separate and are not added to that aggregate. Review security findings before
merging, without treating every static-analysis warning as an automatic release
blocker.

Maintainers can inspect or edit default setup under **Settings > Advanced
Security > CodeQL analysis**. Start with the default suite and evaluate its
signal before expanding queries or the threat model. The remote-sources model
is not a claim that every local CLI input is covered. If a concrete requirement
cannot be met by default setup, document the reason before switching to an
advanced workflow, and avoid running both configurations. See GitHub's
[default-setup documentation](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configure-code-scanning).

## Updating Python dependencies

`pyproject.toml` remains the source of compatible runtime, dev, and release
requirements. `requirements/tooling.in` adds only bootstrap pip and the generator
from `requirements/generator.txt`. The latter pins uv independently, so a stale
or invalid generated closure cannot prevent installing the resolver.

The [uv universal resolver](https://docs.astral.sh/uv/concepts/resolution/)
generates `requirements/tooling.txt` for the complete Python 3.11–3.14 range on
Linux and Windows, selected in `[tool.uv].environments`. Conditional dependencies
retain environment markers; this is not a lock of only the developer's platform.
`requirements/build.txt` continues to constrain isolated builds separately.
Adding a supported Python version/platform requires extending this target policy
and the CI matrix together.

Bootstrap the generator once:

```bash
python -m pip install -r requirements/generator.txt
```

Regenerate the constraints and align pre-commit Ruff/Commitizen revisions with
one command from the repository root:

```bash
python .github/scripts/tooling-constraints.py
```

Existing pins are resolution preferences, so regeneration retains reviewed
versions when compatible. It resolves the entire graph and can move a coupled
dependency when needed; it does not force an incompatible transitive pin. For a
deliberate upgrade, request the parent package (repeat the option for several):

```bash
python .github/scripts/tooling-constraints.py --upgrade-package pydantic
```

An exact parent requirement, such as `python-semantic-release`, must first be
changed in `pyproject.toml`. To upgrade uv itself, edit `generator.txt` and
bootstrap it again before regenerating. Do not edit transitive pins by hand.
Ruff and Commitizen must resolve to one version across supported environments;
the generator refuses ambiguous hook versions and preserves hook options.

Verify reproducible regeneration without writing tracked files:

```bash
python .github/scripts/tooling-constraints.py --check
```

This check needs package-index metadata/network access (or an already populated
uv cache). CI runs it in the authoritative quality job, and the existing matrix
installs the constrained dev/release graph and runs `pip check` on every tested
platform/Python combination. Runtime ranges for normal users remain unchanged.

Python dependency updates belong in a dedicated dependency PR:

1. review the direct dependency ranges in `pyproject.toml`;
2. regenerate `requirements/tooling.txt` and hook revisions with the command above; update `requirements/build.txt` separately when needed;
3. use a clean environment and install `.[dev,release]` with the candidate constraints;
4. run `pip check`, the local quality checks, and the full GitHub Actions matrix;
5. verify the real Forgejo integration before merging.

The tooling constraints include the union of relevant conditional dependencies for Python 3.11-3.14, Linux, and Windows. A constraint does not cause a package to be installed by itself; it fixes the version only when required and its marker matches the environment. These pins are not a promise for other platforms or future Python versions.

Dependabot checks both the `pip` ecosystem and GitHub Actions weekly. All Python
updates share one `python-tooling` group, avoiding isolated coupled transitive
updates such as `pydantic-core`. Regenerate and review its proposed changes on
the same PR before merging; the generation check rejects stale/inconsistent
output and hook drift. Dependency PRs never regenerate or merge themselves.
Third-party GitHub Actions remain pinned to full commit SHAs, with the
corresponding major version documented inline.

## Adding a publisher

Keep registry-specific behavior in `src/forge_publish/publishers/`.

A publisher should validate inputs, construct the Forgejo endpoint explicitly, support dry-run mode, avoid exposing credentials, and raise application-specific errors for expected failures.
