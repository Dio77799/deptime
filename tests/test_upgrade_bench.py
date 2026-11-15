"""DT-QA-21's scorer (`bench/upgrade-check/run.py`) on a synthetic set and the synthetic httpx index. Offline."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bench" / "holdout"))
_spec = importlib.util.spec_from_file_location(
    "upgrade_check_run", ROOT / "bench" / "upgrade-check" / "run.py"
)
assert _spec is not None and _spec.loader is not None
bench = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bench)

CODE = """import httpx

client = httpx.Client(proxies="http://p", timeout=5)
client.get("https://example.invalid")
"""


def _set(tmp_path: Path) -> tuple[Path, Path]:
    holdout, sources = tmp_path / "holdout", tmp_path / "sources"
    (holdout / "s").mkdir(parents=True)
    rows = [
        {
            "id": "u-break",
            "source": "pinned",
            "repo": "https://github.com/o/a",
            "commit": "c1",
            "package": "httpx",
            "from": "0.27.2",
            "to": "0.28.1",
        },
        {
            "id": "u-clean",
            "source": "pinned",
            "repo": "https://github.com/o/b",
            "commit": "c2",
            "package": "httpx",
            "from": "0.27.2",
            "to": "0.27.2",
        },
    ]
    call = {"kind": "call", "path": "httpx.Client", "npos": 0, "kwargs": ["proxies", "timeout"]}
    labels = [
        {
            "id": "u-break",
            "items": [
                {**call, "label": "breaks", "change": "param_removed"},
                {
                    "kind": "call",
                    "path": "httpx.Client.get",
                    "npos": 1,
                    "kwargs": [],
                    "via": "instance",
                    "label": "works",
                },
                {"kind": "name", "path": "httpx.Gone", "label": "excluded", "why": "pinned"},
            ],
        },
        {
            "id": "u-clean",
            "items": [{**call, "label": "works"}, {"kind": "name", "path": "httpx.Nope", "label": "works"}],
        },
    ]
    (holdout / "s" / "upgrades.jsonl").write_text("\n".join(map(json.dumps, rows)))
    (holdout / "s" / "labels.jsonl").write_text("\n".join(map(json.dumps, labels)))
    for slug in ("o__a@c1", "o__b@c2"):
        (sources / slug).mkdir(parents=True)
        (sources / slug / "main.py").write_text(CODE)  # present: nothing is fetched
    return holdout, sources


def test_scores_each_labelled_use_and_each_upgrade(tmp_path, dt):
    holdout, sources = _set(tmp_path)
    uses, upgrades, unavailable = bench.run(dt, sources, ["s"], holdout)
    assert unavailable == []
    got = {
        (u["upgrade"], u["path"]): (u["label"], u["read"], u["flagged"], u["per_use_flagged"]) for u in uses
    }
    assert got == {
        ("u-break", "httpx.Client"): ("breaks", True, True, True),
        ("u-break", "httpx.Client.get"): ("works", True, False, False),
        ("u-clean", "httpx.Client"): ("works", True, False, False),
        ("u-clean", "httpx.Nope"): (
            "works",
            False,
            False,
            True,
        ),  # not in the code: not read; asked directly, missing
    }
    assert [(u["upgrade"], u["clean"], u["fails"]) for u in upgrades] == [
        ("u-break", False, True),
        ("u-clean", True, False),
    ]
    md = "\n".join(bench.report(uses, upgrades, unavailable, "2026-11-15"))
    assert "| breaks found | ≥ 90% | 100.0% | yes |" in md
    assert "| labelled uses the reader reads | ≥ 95% | 75.0% | no |" in md


def test_a_keyword_break_flags_only_calls_that_pass_it():
    class B:
        def __init__(self, path, kind, kwarg=None):
            self.path, self.kind, self.kwarg = path, kind, kwarg

    rejected = [B("httpx.Client", "rejected_kwarg", "proxies")]
    assert bench.flagged({"kind": "call", "path": "httpx.Client", "kwargs": ["proxies"]}, rejected)
    assert not bench.flagged({"kind": "call", "path": "httpx.Client", "kwargs": ["timeout"]}, rejected)
    assert not bench.flagged({"kind": "name", "path": "httpx.Client"}, rejected)
    assert bench.flagged({"kind": "name", "path": "httpx.X"}, [B("httpx.X", "missing")])
    assert not bench.flagged({"kind": "name", "path": "httpx.X"}, [B("httpx.X", "raises")])
