"""Exercise the workflow conditions and the actual aggregate shell script."""

import os
import re
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATIONS = (
    "DEPENDENCY_REVIEW",
    "INTEGRATION",
    "QUALITY",
    "TYPECHECK",
    "PYTHON",
    "WINDOWS",
)


def job(workflow: str, name: str) -> str:
    content = (ROOT / ".github/workflows" / workflow).read_text()
    return re.search(
        rf"^  {name}:\n(.*?)(?=^  \w+:|\Z)", content, re.MULTILINE | re.DOTALL
    ).group(1)


def evaluate(expression: str, github: SimpleNamespace, coverage: str = "skipped"):
    # Only evaluate checked-in expressions, with the small context they use.
    expression = expression.replace("&&", " and ").replace("||", " or ")
    expression = expression.replace("!cancelled()", "not cancelled()")
    expression = " ".join(expression.split())
    return eval(
        expression,
        {"__builtins__": {}},
        {
            "github": github,
            "needs": SimpleNamespace(coverage=SimpleNamespace(result=coverage)),
            "false": False,
            "always": lambda: True,
            "cancelled": lambda: False,
        },
    )


def condition(workflow: str, name: str) -> str:
    return re.search(r"    if: .*?\$\{\{(.*?)\}\}", job(workflow, name), re.DOTALL)[1]


def context(author="contributor", fork=False, draft=False, actor="maintainer"):
    return SimpleNamespace(
        repository="Oxelio/forge-publish",
        event_name="pull_request",
        ref="refs/pull/123/merge",
        actor=actor,
        event=SimpleNamespace(
            pull_request=SimpleNamespace(
                draft=draft,
                user=SimpleNamespace(login=author),
                head=SimpleNamespace(
                    repo=SimpleNamespace(
                        full_name="outside/fork" if fork else "Oxelio/forge-publish"
                    )
                ),
            )
        ),
    )


@pytest.mark.parametrize("actor", ["dependabot[bot]", "maintainer"])
@pytest.mark.parametrize("draft", [False, True])
@pytest.mark.parametrize("fork", [False, True])
@pytest.mark.parametrize("author", ["contributor", "dependabot[bot]", "other[bot]"])
def test_sonar_eligibility_and_reruns(author, fork, draft, actor):
    github = context(author, fork, draft, actor)
    expected = not draft and not fork and author != "dependabot[bot]"
    assert evaluate(condition("ci.yml", "sonar"), github) == expected
    assert evaluate(condition("sonar.yml", "analysis"), github) == expected
    assert evaluate(condition("ci.yml", "gate"), github) == (not draft)


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
@pytest.mark.parametrize("ref", ["refs/heads/main", "refs/heads/topic"])
@pytest.mark.parametrize("coverage", ["success", "skipped", "failure", "cancelled"])
def test_main_analysis_still_requires_coverage(event, ref, coverage):
    github = context()
    github.event_name = event
    github.ref = ref
    assert evaluate(condition("sonar.yml", "analysis"), github, coverage) == (
        ref == "refs/heads/main" and coverage == "success"
    )


def run_gate(github, sonar, **overrides):
    block = job("ci.yml", "gate")
    env = os.environ | {f"{name}_RESULT": "success" for name in VALIDATIONS}
    for name in ("IS_FORK", "IS_DEPENDABOT"):
        expression = re.search(rf"{name}: \$\{{\{{(.*?)\}}\}}", block)[1]
        env[name] = str(evaluate(expression, github)).lower()
    env.update(SONAR_RESULT=sonar, **overrides)
    script = textwrap.dedent(block.split("        run: |\n", 1)[1])
    return subprocess.run(
        ["bash", "-e"],
        input=script,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


bash_only = pytest.mark.skipif(
    sys.platform == "win32" or not shutil.which("bash"),
    reason="The aggregate runs Bash on Linux",
)


@bash_only
@pytest.mark.parametrize(
    "author,fork",
    [
        ("contributor", False),
        ("contributor", True),
        ("dependabot[bot]", False),
        ("dependabot[bot]", True),
    ],
)
@pytest.mark.parametrize("sonar", ["success", "skipped", "failure", "cancelled", ""])
def test_gate_accepts_only_the_expected_sonar_result(author, fork, sonar):
    result = run_gate(context(author, fork), sonar)
    expected = "skipped" if fork or author == "dependabot[bot]" else "success"
    assert (result.returncode == 0) == (sonar == expected), result.stderr


@bash_only
@pytest.mark.parametrize(
    "author,fork",
    [("contributor", False), ("contributor", True), ("dependabot[bot]", False)],
)
@pytest.mark.parametrize("validation", VALIDATIONS)
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_every_other_validation_remains_mandatory(author, fork, validation, result):
    sonar = "skipped" if fork or author == "dependabot[bot]" else "success"
    assert (
        run_gate(
            context(author, fork), sonar, **{f"{validation}_RESULT": result}
        ).returncode
        != 0
    )
