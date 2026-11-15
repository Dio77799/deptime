"""The upgrade questions of DT-QA-18: the 2026-11f holdout's scored uses, one question per upgrade.

Shared by ask.py (which never reads a label beyond the works/breaks/excluded split that picks the scored uses, the
same split DepTime was asked on) and grade.py.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from packaging.version import Version

SET = Path(__file__).resolve().parents[2] / "holdout" / "2026-11f"
SCORED = ("works", "breaks")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def load_upgrades() -> list[dict]:
    """Each upgrade with a scored use, its scored uses in the order labels.jsonl lists them, in the order of the
    sha256 of the upgrade's id: fixed, and no package comes first."""
    rows = {r["id"]: r for r in _jsonl(SET / "upgrades.jsonl")}
    out = []
    for lab in _jsonl(SET / "labels.jsonl"):
        items = [i for i in lab["items"] if i["label"] in SCORED]
        if not items:
            continue
        row = rows[lab["id"]]
        down = Version(row["to"]) < Version(row["from"])
        out.append({**row, "direction": "down" if down else "up", "items": items})
    return sorted(out, key=lambda u: hashlib.sha256(u["id"].encode()).hexdigest())


def render_use(item: dict) -> str:
    """A use as the model reads it: `_` for each argument passed by position, `name=` for each keyword."""
    on = " on an instance" if item.get("via") == "instance" else ""
    if item["kind"] == "call":
        args = ["_"] * (item.get("npos") or 0) + [f"{k}=" for k in item.get("kwargs", [])]
        return f"call{on}: {item['path']}({', '.join(args)})"
    return f"attribute{on}: {item['path']}" if on else item["path"]


def user_message(upgrade: dict) -> str:
    uses = "\n".join(f"{n}. {render_use(i)}" for n, i in enumerate(upgrade["items"], 1))
    return (
        f"Package: {upgrade['package']}\n"
        f"From: {upgrade['from']} (the code works with this release)\n"
        f"To: {upgrade['to']} (the code will run with this release instead)\n\n"
        f"Uses:\n{uses}\n"
    )
