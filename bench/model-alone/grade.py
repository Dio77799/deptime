"""Score the model-alone replies with the traceback benchmark's scorer, beside DepTime's first run (DT-QA-16).

  uv run python bench/model-alone/grade.py > bench/model-alone/results-<date>.md

Reads answers/<model>-run<N>.jsonl (ask.py) and boundaries.json (boundaries.py). The rule is in README.md and was
committed before any model was asked: `deptime.bench.score_case` on the model's answer as if it were
`explain_error`'s first finding, with two allowances that only help the model. A boundary also counts when the answer
names its other side, and the package also counts under one of its import names.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from boundaries import HOLDOUT, load_cases
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version
from pydantic import ValidationError

from deptime.bench import score_case
from deptime.config import Coverage, load_coverage
from deptime.models import ExplainResult, Finding, Replacement

HERE = Path(__file__).parent
ANSWERS = HERE / "answers"
# The models' training data ends in June 2026 (README.md): a break released from this day on is newer than it.
AFTER_CUTOFF = "2026-07-01"
ISSUE_GROUPS = {
    "symbol_removed": "name removed",
    "module_removed": "module removed",
    "param_removed": "parameter removed or now required",
    "param_now_required": "parameter removed or now required",
    "symbol_not_yet_added": "not yet added",
    "param_not_yet_added": "not yet added",
}


def parse_reply(text: str) -> dict | None:
    """The first JSON object in the reply. The prompt asks for nothing else, but a code fence or a sentence around
    it is a slip in form, not a wrong answer."""
    decoder = json.JSONDecoder()
    for start in (m.start() for m in re.finditer(r"\{", text)):
        try:
            value, _ = decoder.raw_decode(text, start)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def clean_symbol(value: object) -> str:
    """Form only: no backticks or spaces, no call brackets after a name (`f()`), and a bare parameter name in the
    parentheses (`f(strict=)`, `f('strict')`)."""
    text = re.sub(r"[\s`]", "", value) if isinstance(value, str) else ""
    text = text.removesuffix("()")
    if (m := re.fullmatch(r"(.+)\((.*)\)", text)) is not None:
        text = f"{m[1].removesuffix('()')}({m[2].strip('\'"*=')})"
    return text


def clean_version(value: object) -> str | None:
    """The dotted number in what the model gave as a version: "v2.31.0" and "2.31.x" read 2.31.0 and 2.31."""
    m = re.search(r"\d+(?:\.\d+)*", value) if isinstance(value, str) else None
    return m[0] if m else None


def to_finding(answer: dict, expected_package: str, coverage: Coverage) -> Finding | None:
    """The answer as an `explain_error` finding, or None when it isn't one (no package or name, an issue that isn't
    one of the six)."""
    package = answer.get("package")
    if not isinstance(package, str) or not clean_symbol(answer.get("symbol")):
        return None
    # An import name for the distribution ("sklearn" for scikit-learn) names the right library.
    spec = coverage.get(expected_package)
    if spec is not None and canonicalize_name(package) in {canonicalize_name(n) for n in spec.import_names}:
        package = expected_package
    replacements = answer.get("replacements")
    targets = [t for t in replacements if isinstance(t, str)] if isinstance(replacements, list) else []
    try:
        return Finding(
            package=package,
            symbol=clean_symbol(answer.get("symbol")),
            defined_at=clean_symbol(answer.get("defined_at")) or None,
            issue=answer.get("issue"),
            last_version_with=clean_version(answer.get("last_version_with")),
            first_version_with=clean_version(answer.get("first_version_with")),
            replacements=[Replacement(target=t, confidence=1.0, source="error_message") for t in targets],
            confidence="high",
            explanation="",
        )
    except ValidationError:
        return None


def other_side(answer: dict, row: dict) -> bool:
    """Does the answer name the far side of the boundary: the first release without a removed name, or the last
    release without one not yet added? To the precision the case asks of DepTime: a prefix of two numbers ("0.27")
    is matched on two (0.28.0 and 0.28.1 both name the release after the 0.27 series)."""
    if row["side"] == "last_version_with":
        given, truth = clean_version(answer.get("first_version_without")), row.get("breaking")
    else:
        given, truth = clean_version(answer.get("last_version_without")), row.get("last_without")
    if not given or not truth:
        return False
    try:
        n = len(Version(row["prefix"]).release)
        have, want = Version(given).release + (0,) * n, Version(truth).release + (0,) * n
    except InvalidVersion:
        return False
    return have[:n] == want[:n]


def grade(case: dict, reply: str, row: dict, coverage: Coverage) -> dict:
    """One reply's marks: the benchmark's root cause, boundary and replacement, and where a miss went wrong."""
    expected = case["expected"]
    marks = {
        "answered": False,
        "root_cause": False,
        "boundary": False,
        "boundary_same_side": False,
        "passed": False,
        "replacement": False if "replacement_contains" in expected else None,
        "miss": "no answer",
    }
    answer = parse_reply(reply)
    finding = to_finding(answer, expected["package"], coverage) if answer else None
    if finding is None:
        return marks
    scored = score_case(case, ExplainResult(signal=None, findings=[finding]), coverage)
    same_side = bool(scored.boundary)
    boundary = same_side or (scored.root_cause and other_side(answer, row))
    if canonicalize_name(finding.package) != canonicalize_name(expected["package"]):
        miss = "package"
    elif not any(s.endswith(expected["symbol_suffix"]) for s in (finding.symbol, finding.defined_at or "")):
        miss = "name"
    elif finding.issue != expected["issue"]:
        miss = "kind of change"
    else:
        miss = None if boundary else "release"
    return {
        "answered": True,
        "root_cause": scored.root_cause,
        "boundary": boundary,
        "boundary_same_side": same_side,
        "passed": scored.root_cause and boundary,
        "replacement": scored.replacement,
        "miss": miss,
    }


def first_run() -> tuple[dict[str, bool], dict[str, tuple[int, int]]]:
    """DepTime's first run, from each set's results file: every case's pass, and the root-cause and replacement
    counts the file reports."""
    passed: dict[str, bool] = {}
    totals = {"root cause": (0, 0), "replacement": (0, 0)}
    for path in sorted(HOLDOUT.glob("*/results-*.md")):
        text = path.read_text(encoding="utf-8")
        for mark, case_id in re.findall(r"^- (PASS|FAIL) `([^`]+)`", text, flags=re.M):
            passed[case_id] = mark == "PASS"
        for key in totals:
            m = re.search(rf"^- {key} [\d.]+% \((\d+)/(\d+)", text, flags=re.M)
            totals[key] = (totals[key][0] + int(m[1]), totals[key][1] + int(m[2]))
    return passed, totals


def pct(hits: int, total: int) -> str:
    return f"{100 * hits / total:.1f}%" if total else "-"


def spread(counts: list[int], total: int) -> str:
    """A range over runs: "61.3% to 64.9% (117, 121, 124 of 191)"; one run is just its figure."""
    if not counts or not total:
        return "-"
    low, high = pct(min(counts), total), pct(max(counts), total)
    span = low if low == high else f"{low} to {high}"
    return f"{span} ({', '.join(str(c) for c in counts)} of {total})"


def main() -> int:
    cases = {c["id"]: c for c in load_cases()}
    rows = json.loads((HERE / "boundaries.json").read_text(encoding="utf-8"))
    coverage = load_coverage()
    deptime, totals = first_run()
    assert set(deptime) == set(cases) == set(rows), (
        "the sets, their first runs and boundaries.json must agree"
    )
    after = {i for i, row in rows.items() if row["released"] >= AFTER_CUTOFF}
    before = set(cases) - after
    with_replacement = [i for i, c in cases.items() if "replacement_contains" in c["expected"]]

    runs: dict[str, dict[int, dict[str, dict]]] = defaultdict(dict)  # model id -> run -> case id -> marks
    tokens: dict[str, list[dict]] = defaultdict(list)
    for path in sorted(ANSWERS.glob("*-run*.jsonl")):
        run = int(path.stem.rsplit("-run", 1)[1])
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if {r["id"] for r in records} != set(cases):
            print(f"{path.name}: {len(records)} of {len(cases)} cases answered; left out", file=sys.stderr)
            continue
        (model,) = {r["model_id"] for r in records}
        runs[model][run] = {
            r["id"]: grade(cases[r["id"]], r["reply"], rows[r["id"]], coverage) for r in records
        }
        tokens[model] += records

    def count(marks: dict[str, dict], key: str, ids) -> int:
        return sum(bool(marks[i][key]) for i in ids)

    out = [
        "| Answered by | Right package, name and breaking release | Break released by 2026-06-30 | Break released"
        " after | Root cause, release aside | Right replacement in the first three |",
        "|---|---|---|---|---|---|",
        f"| DepTime, first run | {spread([sum(deptime.values())], len(cases))}"
        f" | {spread([sum(deptime[i] for i in before)], len(before))}"
        f" | {spread([sum(deptime[i] for i in after)], len(after))}"
        f" | {spread([totals['root cause'][0]], totals['root cause'][1])}"
        f" | {spread([totals['replacement'][0]], totals['replacement'][1])} |",
    ]
    for model, by_run in sorted(runs.items()):
        marks = [by_run[n] for n in sorted(by_run)]
        out.append(
            f"| `{model}` alone, {len(marks)} run{'s' if len(marks) > 1 else ''}"
            f" | {spread([count(m, 'passed', cases) for m in marks], len(cases))}"
            f" | {spread([count(m, 'passed', before) for m in marks], len(before))}"
            f" | {spread([count(m, 'passed', after) for m in marks], len(after))}"
            f" | {spread([count(m, 'root_cause', cases) for m in marks], len(cases))}"
            f" | {spread([count(m, 'replacement', with_replacement) for m in marks], len(with_replacement))} |"
        )

    out += [
        "",
        "## Each run",
        "",
        "| Model | Run | Answered | Root cause | + boundary (headline) | + boundary, same side only | Replacement |",
        "|---|---|---|---|---|---|---|",
    ]
    for model, by_run in sorted(runs.items()):
        for n, m in sorted(by_run.items()):
            out.append(
                f"| `{model}` | {n} | {count(m, 'answered', cases)} | {count(m, 'root_cause', cases)}"
                f" | {count(m, 'passed', cases)} ({pct(count(m, 'passed', cases), len(cases))})"
                f" | {sum(m[i]['root_cause'] and m[i]['boundary_same_side'] for i in cases)}"
                f" | {count(m, 'replacement', with_replacement)} of {len(with_replacement)} |"
            )

    out += [
        "",
        "## Where the misses are",
        "",
        "The first thing wrong in each missed answer, as a mean per run.",
        "",
        "| Model | No answer | Package | Name | Kind of change | Release |",
        "|---|---|---|---|---|---|",
    ]
    kinds = ("no answer", "package", "name", "kind of change", "release")
    for model, by_run in sorted(runs.items()):
        cells = [sum(m[i]["miss"] == k for m in by_run.values() for i in cases) / len(by_run) for k in kinds]
        out.append(f"| `{model}` | " + " | ".join(f"{c:.1f}" for c in cells) + " |")

    groups = sorted(set(ISSUE_GROUPS.values()))
    in_group = {g: [i for i, c in cases.items() if ISSUE_GROUPS[c["expected"]["issue"]] == g] for g in groups}
    out += [
        "",
        "## By kind of change",
        "",
        "Right package, name and breaking release; for a model, the range over its runs.",
        "",
        "| Answered by | " + " | ".join(f"{g} ({len(in_group[g])})" for g in groups) + " |",
        "|---|" + "---|" * len(groups),
        "| DepTime, first run | "
        + " | ".join(pct(sum(deptime[i] for i in in_group[g]), len(in_group[g])) for g in groups)
        + " |",
    ]
    for model, by_run in sorted(runs.items()):
        cells = []
        for g in groups:
            shares = [pct(count(m, "passed", in_group[g]), len(in_group[g])) for m in by_run.values()]
            low, high = min(shares, key=lambda s: float(s[:-1])), max(shares, key=lambda s: float(s[:-1]))
            cells.append(low if low == high else f"{low} to {high}")
        out.append(f"| `{model}` | " + " | ".join(cells) + " |")

    out += [
        "",
        "## Case by case",
        "",
        'A model has a case when most of its runs do. "Same in every run" counts the cases all its runs agree on,'
        " right or wrong.",
        "",
        "| Model | Both right | Only DepTime | Only the model | Neither | Same in every run |",
        "|---|---|---|---|---|---|",
    ]
    for model, by_run in sorted(runs.items()):
        marks = list(by_run.values())
        has = {i: 2 * sum(m[i]["passed"] for m in marks) > len(marks) for i in cases}
        steady = sum(len({m[i]["passed"] for m in marks}) == 1 for i in cases)
        out.append(
            f"| `{model}` | {sum(has[i] and deptime[i] for i in cases)} | {sum(deptime[i] and not has[i] for i in cases)}"
            f" | {sum(has[i] and not deptime[i] for i in cases)} | {sum(not has[i] and not deptime[i] for i in cases)}"
            f" | {steady} of {len(cases)} |"
        )

    out += [
        "",
        "## What each answer took",
        "",
        "| Model | Calls | Mean tokens in | Mean tokens out | of which thinking | Mean seconds |",
        "|---|---|---|---|---|---|",
    ]
    for model, records in sorted(tokens.items()):
        n = len(records)

        def mean(key: str, records: list[dict] = records, n: int = n) -> str:
            return f"{sum(r.get(key) or 0 for r in records) / n:,.0f}"

        out.append(
            f"| `{model}` | {n} | {mean('input_tokens')} | {mean('output_tokens')} | {mean('thinking_tokens')} | {mean('seconds')} |"
        )
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
