"""The model-alone baseline's scoring rule (DT-QA-16, bench/model-alone). Offline: no model is called and PyPI isn't
read."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from packaging.version import Version

from deptime.config import load_coverage

sys.path.insert(0, str(Path(__file__).parent.parent / "bench" / "model-alone"))
import ask
import boundaries
import grade

COVERAGE = load_coverage()
REMOVED = {
    "id": "t-removed",
    "source": "constructed",
    "traceback": "TypeError: Client.__init__() got an unexpected keyword argument 'proxies'",
    "installed": {"httpx": "0.28.1"},
    "expected": {
        "package": "httpx",
        "symbol_suffix": "Client.__init__(proxies)",
        "issue": "param_removed",
        "last_version_with": "0.27",
        "replacement_contains": "proxy",
    },
}
REMOVED_ROW = {"side": "last_version_with", "prefix": "0.27", "last_with": "0.27.2", "breaking": "0.28.0"}
NOT_YET = {
    "id": "t-not-yet",
    "source": "constructed",
    "traceback": "ImportError: cannot import name 'LLM' from 'crewai'",
    "installed": {"crewai": "0.63.1"},
    "expected": {
        "package": "crewai",
        "symbol_suffix": "crewai.LLM",
        "issue": "symbol_not_yet_added",
        "first_version_with": "0.63.2",
    },
}
NOT_YET_ROW = {
    "side": "first_version_with",
    "prefix": "0.63.2",
    "breaking": "0.63.2",
    "last_without": "0.63.1",
}


def _reply(**fields: object) -> str:
    answer = {
        "package": "httpx",
        "symbol": "httpx.Client.__init__(proxies)",
        "defined_at": None,
        "issue": "param_removed",
        "last_version_with": None,
        "first_version_without": None,
        "last_version_without": None,
        "first_version_with": None,
        "replacements": [],
    }
    return json.dumps({**answer, **fields})


def test_the_benchmarks_own_side_of_the_boundary_passes() -> None:
    marks = grade.grade(
        REMOVED, _reply(last_version_with="0.27.2", replacements=["proxy"]), REMOVED_ROW, COVERAGE
    )
    assert marks["passed"] and marks["boundary_same_side"] and marks["replacement"] and marks["miss"] is None


def test_the_other_side_of_the_boundary_passes_to_the_prefixs_precision() -> None:
    for version in ("0.28.0", "0.28", "v0.28.1"):  # the case says "0.27", so two numbers are compared
        marks = grade.grade(REMOVED, _reply(first_version_without=version), REMOVED_ROW, COVERAGE)
        assert marks["passed"] and not marks["boundary_same_side"], version
    marks = grade.grade(REMOVED, _reply(first_version_without="0.29.0"), REMOVED_ROW, COVERAGE)
    assert marks["root_cause"] and not marks["passed"] and marks["miss"] == "release"


def test_one_right_side_is_enough() -> None:
    reply = _reply(last_version_with="0.25.0", first_version_without="0.28.0")
    assert grade.grade(REMOVED, reply, REMOVED_ROW, COVERAGE)["passed"]


def test_a_right_release_doesnt_count_without_the_root_cause() -> None:
    for fields, miss in (
        ({"package": "requests"}, "package"),
        ({"symbol": "httpx.Client.__init__(proxy)"}, "name"),
        ({"issue": "symbol_removed"}, "kind of change"),
    ):
        marks = grade.grade(REMOVED, _reply(last_version_with="0.27.2", **fields), REMOVED_ROW, COVERAGE)
        assert not marks["root_cause"] and not marks["boundary"] and not marks["passed"]
        assert marks["miss"] == miss and marks["replacement"] is False


def test_not_yet_added_takes_either_side_and_three_numbers_exactly() -> None:
    reply = dict(package="crewai", symbol="crewai.LLM", issue="symbol_not_yet_added")
    assert grade.grade(NOT_YET, _reply(**reply, first_version_with="0.63.2"), NOT_YET_ROW, COVERAGE)["passed"]
    assert grade.grade(NOT_YET, _reply(**reply, last_version_without="0.63.1"), NOT_YET_ROW, COVERAGE)[
        "passed"
    ]
    marks = grade.grade(NOT_YET, _reply(**reply, last_version_without="0.63.0"), NOT_YET_ROW, COVERAGE)
    assert not marks["passed"] and marks["replacement"] is None  # the case expects no replacement
    # The removal fields aren't read for a name not yet added.
    assert not grade.grade(NOT_YET, _reply(**reply, first_version_without="0.63.2"), NOT_YET_ROW, COVERAGE)[
        "passed"
    ]


def test_form_isnt_marked() -> None:
    fenced = "Here is the answer:\n```json\n" + _reply(last_version_with="0.27.x") + "\n```"
    assert grade.grade(REMOVED, fenced, REMOVED_ROW, COVERAGE)["passed"]
    spelled = _reply(symbol="`httpx.Client.__init__(proxies=)`", last_version_with="v0.27.2")
    assert grade.grade(REMOVED, spelled, REMOVED_ROW, COVERAGE)["passed"]
    assert grade.clean_symbol("pkg.mod.func()") == "pkg.mod.func"
    assert grade.clean_symbol("pkg.f('strict')") == "pkg.f(strict)"


def test_an_import_name_counts_as_the_package() -> None:
    case = {
        **REMOVED,
        "expected": {
            "package": "scikit-learn",
            "symbol_suffix": "metrics.SCORERS",
            "issue": "symbol_removed",
            "last_version_with": "1.2",
        },
    }
    row = {"side": "last_version_with", "prefix": "1.2", "last_with": "1.2.2", "breaking": "1.3.0"}
    reply = _reply(
        package="sklearn",
        symbol="sklearn.metrics.SCORERS",
        issue="symbol_removed",
        first_version_without="1.3",
    )
    assert grade.grade(case, reply, row, COVERAGE)["passed"]
    assert not grade.grade(case, reply.replace('"sklearn"', '"scipy"'), row, COVERAGE)["root_cause"]


def test_what_isnt_an_answer_is_wrong() -> None:
    for reply in (
        "I can't tell.",
        "[1, 2]",
        _reply(issue="deprecated"),
        _reply(symbol=""),
        _reply(package=None),
    ):
        marks = grade.grade(REMOVED, reply, REMOVED_ROW, COVERAGE)
        assert not marks["answered"] and not marks["passed"] and marks["miss"] == "no answer", reply


def test_boundaries_from_a_release_list() -> None:
    days = {
        Version(v): f"2024-01-{n:02}"
        for n, v in enumerate(("0.26.0", "0.27.0", "0.27.2", "0.28.0", "0.28.1"), 1)
    }
    removed = boundaries.boundary({"last_version_with": "0.27"}, days)
    assert (removed["last_with"], removed["breaking"], removed["released"]) == (
        "0.27.2",
        "0.28.0",
        "2024-01-04",
    )
    added = boundaries.boundary({"first_version_with": "0.27"}, days)
    assert (added["breaking"], added["last_without"], added["released"]) == ("0.27.0", "0.26.0", "2024-01-02")
    assert boundaries.matches(Version("1.5.3"), "1.5") and not boundaries.matches(Version("1.50.0"), "1.5")
    assert boundaries.matches(Version("2"), "2.0")


def test_the_committed_boundaries_cover_every_case() -> None:
    rows = json.loads(boundaries.OUT.read_text(encoding="utf-8"))
    cases = boundaries.load_cases()
    assert len(cases) == 191 and {c["id"] for c in cases} == set(rows)
    assert all(row["breaking"] and row["released"] for row in rows.values())
    assert sum(row["released"] >= grade.AFTER_CUTOFF for row in rows.values()) == 22


def test_the_model_is_given_only_the_versions_and_the_traceback() -> None:
    message = ask.user_message(REMOVED)
    assert message == "Installed versions:\nhttpx==0.28.1\n\nTraceback:\n" + REMOVED["traceback"] + "\n"
    for case in boundaries.load_cases():
        # Nothing of the expected answer's own fields is in what a case sends, beyond what its traceback says.
        assert set(json.loads(json.dumps(case)).keys()) >= {"traceback", "installed", "expected"}
        assert "symbol_suffix" not in ask.user_message(case) and "evidence" not in ask.user_message(case)
    order = [c["id"] for c in ask.ordered_cases()]
    assert order == [c["id"] for c in ask.ordered_cases()] and len(set(order)) == 191
    assert (
        "--tools" in ask.command("haiku")
        and ask.command("haiku")[ask.command("haiku").index("--tools") + 1] == ""
    )


def test_first_run_figures_are_the_readmes() -> None:
    passed, totals = grade.first_run()
    assert (sum(passed.values()), len(passed)) == (166, 191)
    assert totals == {"root cause": (167, 191), "replacement": (41, 85)}
