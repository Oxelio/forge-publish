# Development

## Setup

Python 3.11 through 3.14 are supported.

```bash
python -m venv .venv
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

## CI

Pull requests run:

- Ruff linting
- Ruff formatting verification
- universal tooling-constraints regeneration and Ruff/Commitizen hook alignment
- unit tests with coverage
- dependency review for pull request dependency changes, blocking newly introduced high/critical known vulnerabilities
- wheel and sdist build verification
- Python 3.11, 3.12, and 3.13 compatibility jobs on Linux, including dev/release dependency resolution and `pip check`
- the full quality suite on Python 3.14
- Windows compatibility on Python 3.11 and 3.14, including dev/release dependency resolution and `pip check`

The repository ruleset continues to require the `Quality checks` status. CI runs Dependency Review, the main quality suite, Forgejo integration, the Linux compatibility matrix, and the Windows compatibility matrix in parallel. A final job named `Quality checks` depends on all five groups and fails unless every group succeeds.

Dependency Review evaluates only dependency changes introduced by the pull request and fails for newly introduced known vulnerabilities with high or critical severity. It uses read-only repository contents permission and reports findings through the GitHub Actions check output. License enforcement is explicitly disabled until the project defines a dependency-license policy. Dependabot remains enabled for weekly GitHub Actions and Python dependency updates; it is complementary to this merge-time review rather than replaced by it.

The Forgejo integration workflow starts a digest-pinned Forgejo 16.0.5 image with an ephemeral self-signed TLS certificate and validates real Generic, Debian, and NPM publication through the CLI. Node.js is pinned to 24.21.0. NPM publication is exercised twice against the same Forgejo instance: once with the npm version bundled with that pinned Node.js runtime and once after explicitly installing and verifying the minimum supported npm 11.0.0. The two publications use distinct package versions so both compatibility paths are validated without hard-coding an assumed bundled npm version. The workflow also verifies that Forgejo rejects invalid credentials.

For NPM, both compatibility publications deliberately include conflicting project-local NPM authentication and TLS settings plus conflicting `publishConfig.registry` and `publishConfig.strict-ssl` values. Each publish must still use the temporary Forgejo credentials and verified TLS through Node's `NODE_EXTRA_CA_CERTS` mechanism.

The shared `tests/fixtures/npm_lifecycle` fixture records harmless pack-hook events and rejects credential environment variables or authenticated publish hooks. Both npm compatibility publications verify that no pack hook runs by default, even with project `ignore-scripts=false`. A third publication uses explicit `--allow-pack-scripts` consent with the minimum npm version and project `ignore-scripts=true`, verifying all three pack hooks and preserving script-free authenticated publication. The local pytest lifecycle tests execute real npm pack when supported npm is available, intercept the upload, and inspect the archive with fake tokens; these tests skip when npm is absent or unsupported, while Forgejo CI always provisions supported npm. Unit tests verify that unsupported npm is rejected in both modes before packing or creating authentication files.

Distribution verification installs both the built wheel and the built source distribution into separate clean virtual environments, runs `pip check`, and exercises the installed CLI from each artifact. Release dependencies are validated with `pip check` as well.

Development, CI, integration, and release environments use `requirements/tooling.txt` as an exact constraints set while `pyproject.toml` keeps compatible dependency ranges for normal forge-publish users. Isolated PEP 517 builds use the separate `requirements/build.txt` build constraint so the build backend is deterministic as well. pip itself is pinned in these controlled environments.

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
