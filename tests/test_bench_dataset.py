"""The public benchmark (DT-OSS-14, bench/dataset): its scorer's rules, its frozen v1 contents and a reproducible pack.
Offline; reads only committed files."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

DATASET = Path(__file__).parent.parent / "bench" / "dataset"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"dataset_{name}", DATASET / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


score = _load("score")
build = _load("build")


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _use(i: str, label: str, upgrade: str = "u1", collection: str = "c1") -> dict:
    rec = {
        "id": i,
        "collection": collection,
        "upgrade": upgrade,
        "direction": "up",
        "use": {"kind": "name", "path": f"pkg.{i}"},
        "label": label,
    }
    if label == "breaks":
        rec["change"] = "removed"
    return rec


def test_score_needs_only_the_standard_library() -> None:
    tree = ast.parse((DATASET / "score.py").read_text(encoding="utf-8"))
    roots = {
        (n.module if isinstance(n, ast.ImportFrom) else a.name).split(".")[0]
        for n in ast.walk(tree)
        if isinstance(n, ast.Import | ast.ImportFrom)
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert roots <= set(sys.stdlib_module_names) | {"__future__"}, roots


def test_uses_abstentions_count_as_not_flagged(tmp_path: Path) -> None:
    items = [
        _use("a", "breaks"),
        _use("b", "breaks"),
        _use("c", "breaks"),
        _use("d", "works"),
        _use("e", "works", upgrade="u2"),
        _use("f", "works", upgrade="u2"),
    ]
    preds = {
        "a": {"id": "a", "breaks": True},
        "b": {"id": "b", "breaks": None},
        # c: no prediction
        "d": {"id": "d", "breaks": True},
        "e": {"id": "e", "breaks": False},
        "f": {"id": "f", "breaks": None},
    }
    _, s = score.score_uses(items, preds)
    assert (s["tp"], s["fn"], s["fp"], s["tn"]) == (1, 2, 1, 2)
    assert (s["abstain_breaks"], s["abstain_works"], s["missing_predictions"]) == (2, 1, 1)
    assert s["breaks_found"] == pytest.approx(1 / 3)
    # u2 is the only upgrade where everything works, and nothing in it was flagged.
    assert (s["clean_upgrades"], s["clean_upgrades_with_a_false_alarm"]) == (1, 0)


def test_uses_reject_unknown_ids_duplicates_and_bad_values(tmp_path: Path) -> None:
    _write(tmp_path / "uses.jsonl", [_use("a", "breaks")])
    with pytest.raises(SystemExit, match="no item"):
        score.main(["--data", str(tmp_path), "--uses", str(_write(tmp_path / "p1.jsonl", [{"id": "z"}]))])
    dup = _write(tmp_path / "p2.jsonl", [{"id": "a", "breaks": True}, {"id": "a", "breaks": False}])
    with pytest.raises(SystemExit, match="second prediction"):
        score.main(["--data", str(tmp_path), "--uses", str(dup)])
    bad = _write(tmp_path / "p3.jsonl", [{"id": "a", "breaks": "yes"}])
    with pytest.raises(SystemExit, match="true, false or null"):
        score.main(["--data", str(tmp_path), "--uses", str(bad)])


def test_collection_filter(tmp_path: Path) -> None:
    _write(tmp_path / "uses.jsonl", [_use("a", "breaks"), _use("b", "breaks", collection="c2")])
    preds = _write(tmp_path / "p.jsonl", [{"id": "a", "breaks": True}])
    out = tmp_path / "s.json"
    score.main(["--data", str(tmp_path), "--uses", str(preds), "--collection", "c1", "--json", str(out)])
    assert json.loads(out.read_text())["uses"]["breaks_found"] == 1.0


EXPECTED = {
    "package": "Google-GenerativeAI",
    "symbol_suffix": "Client.__init__(proxies)",
    "issue": "param_removed",
    "last_version_with": "0.27",
    "replacement_contains": "mounts",
}


@pytest.mark.parametrize(
    ("finding", "root", "passed", "replacement"),
    [
        # The package as PyPI compares names; the name through `defined_at`; the boundary as a prefix.
        (
            {
                "package": "google_generativeai",
                "symbol": "x.AsyncClient",
                "defined_at": "x._client.Client.__init__(proxies)",
                "issue": "param_removed",
                "last_version_with": "0.27.2",
                "replacements": ["a", "b", "x.Client(mounts=)"],
            },
            True,
            True,
            True,
        ),
        # Right root cause, wrong release; the replacement is fourth.
        (
            {
                "package": "google-generativeai",
                "symbol": "x.Client.__init__(proxies)",
                "issue": "param_removed",
                "last_version_with": "0.28.0",
                "replacements": ["a", "b", "c", "mounts"],
            },
            True,
            False,
            False,
        ),
        # Another kind of change: nothing else counts.
        (
            {
                "package": "google-generativeai",
                "symbol": "x.Client.__init__(proxies)",
                "issue": "symbol_removed",
                "last_version_with": "0.27.2",
                "replacements": ["mounts"],
            },
            False,
            False,
            False,
        ),
    ],
)
def test_traceback_rules(finding: dict, root: bool, passed: bool, replacement: bool) -> None:
    m = score.judge({"expected": EXPECTED}, [finding])
    assert (m["root_cause"], m["passed"], m["replacement"]) == (root, passed, replacement)


def test_no_finding_and_blame(tmp_path: Path) -> None:
    assert score.judge({"expected": EXPECTED}, [])["answered"] is False
    items = [
        {"id": "n1", "split": "not-api-change", "collection": "f", "expected": None},
        {"id": "n2", "split": "not-api-change", "collection": "f", "expected": None},
        {"id": "n3", "split": "not-api-change", "collection": "f", "expected": None},
    ]
    preds = {
        "n1": {"id": "n1", "findings": [{"issue": "never_existed"}, {"issue": "symbol_removed"}]},
        "n2": {"id": "n2", "findings": [{"issue": "never_existed"}]},
    }
    _, s = score.score_tracebacks(items, preds)
    assert s["not-api-change"] == {"cases": 3, "blamed": 1}


def test_v1_is_frozen() -> None:
    """v1's contents don't change: a corrected label or a new set is a new version (README.md)."""
    uses = build.uses()
    assert len(uses) == 24_873
    assert sum(u["label"] == "breaks" for u in uses) == 1_287
    assert len({u["upgrade"] for u in uses}) == 1_884
    assert len({u["package"] for u in uses}) == 53
    assert all(u["label"] in ("works", "breaks") for u in uses)
    assert all(("change" in u) == (u["label"] == "breaks") for u in uses)
    tracebacks = build.tracebacks()
    splits = {s: sum(t["split"] == s for t in tracebacks) for s in ("holdout", "dev", "not-api-change")}
    assert splits == {"holdout": 191, "dev": 202, "not-api-change": 30}
    assert all((t["expected"] is None) == (t["split"] == "not-api-change") for t in tracebacks)


def test_pack_is_reproducible(tmp_path: Path) -> None:
    digests = []
    for side in ("a", "b"):
        out = tmp_path / side / "bundle"
        build.build(out)
        (out / "predictions").mkdir()
        tar = build.pack(out)
        digests.append(hashlib.sha256(tar.read_bytes()).hexdigest())
    assert digests[0] == digests[1]
