"""Collect DT-QA-22's set: recent Dependabot and Renovate pull requests that update a covered package, by the rule in
README.md here. Nothing here runs DepTime's check or any project's code: sources are downloaded as tarballs and only
parsed, with the holdout's own reader (`bench/holdout/uses.py`).

    uv run python bench/upgrade-check/prs/find_prs.py <work dir> [--packages a,b]

Resumable: <work dir>/selection.json grows one package at a time, and a package already done is skipped. When every
package is done, selection.json and upgrades.jsonl are written here. Sources go to <work dir>/sources/<owner>__<repo>@<sha>/.
"""

from __future__ import annotations

import argparse
import heapq
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path, PurePosixPath

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

HERE = Path(__file__).resolve().parent
HOLDOUT = HERE.parent.parent / "holdout"
sys.path.insert(0, str(HOLDOUT))

from collect import COV, upgrade  # noqa: E402  (the holdout's collector: uses.py and the 40-use cap)
from find_pinned import MIN_USES, earlier_repos, fetch_source, gh  # noqa: E402

from deptime.config import Settings  # noqa: E402
from deptime.index.location import open_index  # noqa: E402

START, END = "2026-08-15", "2026-11-14"  # creation window
CUTOFF = (
    "2026-11-15"  # the probe's newest releases: PyPI as of this day (envs.py reads it from selection.json)
)
PER_STRATUM = 3
MAX_RESULTS = 1000  # GitHub search's limit per query
KEEP = (".py", ".txt", ".toml", ".cfg", ".lock", ".in", ".gitignore")
SETS = ("2026-11", "2026-11b", "2026-11c", "2026-11d", "2026-11e", "2026-11f")
OWN_REPO = "cschmertz/deptime"
BOTS = {
    "dependabot": 'is:pr is:public author:app/dependabot "Bump {name} from" in:title',
    "renovate": 'is:pr is:public author:app/renovate "dependency {name} to" in:title',
}
_PREFIX = r"^(?:\[[^\]]+\]\s*)?(?:[^:]{1,40}:\s*)?"  # `[Security] `, then any short prefix ending in `:`
DEPENDABOT = re.compile(_PREFIX + r"[Bb]ump (\S+) from (\S+) to (\S+?)(?: in (\S+))?\s*$")
RENOVATE = re.compile(_PREFIX + r"[Uu]pdate dependency (\S+) to v?\S+(?:\s.*)?$")
_TICKED = re.compile(r"`([^`]+)`\s*(?:->|→)\s*`([^`]+)`")
_MANIFEST = re.compile(
    r"(^|/)(requirements[^/]*\.txt|[^/]+\.in|pyproject\.toml|uv\.lock|poetry\.lock|pdm\.lock|Pipfile|Pipfile\.lock"
    r"|setup\.py|setup\.cfg)$|(^|/)requirements[^/]*/(.+/)?[^/]+\.txt$"
)


def exact(raw: str) -> str | None:
    """A single exact version (`==1.2.3`, `1.2.3`, `v1.2.3`), else None: a range doesn't qualify."""
    raw = raw.strip().removeprefix("===").removeprefix("==").removeprefix("v").strip()
    if not raw or re.search(r"[\s,^~<>=!*]", raw):
        return None
    try:
        Version(raw)
    except InvalidVersion:
        return None
    return raw


def renovate_versions(body: str, package: str) -> tuple[str, str] | None:
    """The `from` and `to` in the row for `package` of Renovate's table."""
    for line in (body or "").splitlines():
        cells = [c.strip() for c in line.split("|")]
        if len(cells) < 3 or not line.lstrip().startswith("|"):
            continue
        m = re.match(r"\[?([A-Za-z0-9_.\-]+)", cells[1])
        if not m or canonicalize_name(m.group(1)) != package:
            continue
        for cell in cells[2:]:
            if t := _TICKED.search(cell):
                a, b = exact(t.group(1)), exact(t.group(2))
                return (a, b) if a and b else None
    return None


def parse(item: dict, package: str) -> tuple[str, str, str | None] | str:
    """(from, to, Dependabot's directory or None) for a single-package update of `package`, else why not."""
    title = item["title"].strip()
    if item["bot"] == "dependabot":
        m = DEPENDABOT.match(title)
        if not m or canonicalize_name(m.group(1)) != package:
            return "not a single-package update of it"
        a, b = exact(m.group(2)), exact(m.group(3))
        if not (a and b):
            return "versions aren't exact"
        return a, b, (m.group(4) or "/")
    m = RENOVATE.match(title)
    if not m or canonicalize_name(m.group(1)) != package:
        return "not a single-package update of it"
    found = renovate_versions(item.get("body") or "", package)
    if found is None:
        return "no exact versions in the body's table"
    return found[0], found[1], None


def major(a: str, b: str) -> bool:
    x, y = (*Version(a).release, 0, 0), (*Version(b).release, 0, 0)
    return x[0] != y[0] or (x[0] == 0 and x[1] != y[1])


def project_dir(item: dict, dependabot_dir: str | None, manifests: list[str]) -> str:
    """The directory the Action would be pointed at, relative to the repository's root ("" for the root)."""
    if dependabot_dir is not None:
        return dependabot_dir.strip("/")
    parents = [PurePosixPath(f).parent.parts for f in manifests]
    common: list[str] = []
    for parts in zip(*parents, strict=False):
        if len(set(parts)) != 1:
            break
        common.append(parts[0])
    if common and common[-1].lower().startswith("requirements"):
        common.pop()
    return "/".join(common)


def search(bot: str, name: str):
    """One query's results, newest first, page by page, each tagged with its bot."""
    q = BOTS[bot].format(name=name) + f" created:{START}..{END}"
    for page in range(1, MAX_RESULTS // 100 + 1):
        doc = json.loads(
            gh(
                "api",
                "-X",
                "GET",
                "search/issues",
                "-f",
                f"q={q}",
                "-f",
                "sort=created",
                "-f",
                "order=desc",
                "-f",
                "per_page=100",
                "-f",
                f"page={page}",
            )
        )
        time.sleep(7)  # search allows 30 requests a minute; stay well under the secondary limits
        items = doc.get("items", [])
        for it in items:
            yield {**it, "bot": bot}
        if len(items) < 100:
            return


def merged(package: str):
    names = [package] + ([package.replace("-", "_")] if "-" in package else [])
    streams = [search(bot, n) for bot in BOTS for n in names]
    seen: set[str] = set()
    for it in heapq.merge(*streams, key=lambda x: x["created_at"], reverse=True):
        if it["html_url"] not in seen:
            seen.add(it["html_url"])
            yield it


_repo_info: dict[str, dict] = {}


def repo_info(repo: str) -> dict:
    if repo not in _repo_info:
        _repo_info[repo] = json.loads(gh("api", f"repos/{repo}"))
    return _repo_info[repo]


def candidates(package: str, indexed: set[str], skip: set[str], sources: Path, log: list) -> list[dict]:
    spec = COV[package]
    roots = tuple(spec.import_names)
    kept: list[dict] = []
    taken: set[str] = set()
    full = {"major": 0, "other": 0}
    for it in merged(package):
        if min(full.values()) >= PER_STRATUM:
            break
        repo = it["repository_url"].removeprefix("https://api.github.com/repos/")
        entry = {"package": package, "url": it["html_url"], "bot": it["bot"], "title": it["title"]}
        log.append(entry)
        got = parse(it, package)
        if isinstance(got, str):
            entry["skipped"] = got
            continue
        a, b, ddir = got
        entry.update({"from": a, "to": b})
        if Version(a).is_prerelease or Version(b).is_prerelease or Version(a) >= Version(b):
            entry["skipped"] = "not an update between final releases"
            continue
        if a not in indexed or b not in indexed:
            entry["skipped"] = f"not indexed: {', '.join(v for v in (a, b) if v not in indexed)}"
            continue
        stratum = "major" if major(a, b) else "other"
        entry["stratum"] = stratum
        if repo.lower() in skip or repo.lower() == OWN_REPO:
            entry["skipped"] = "in a holdout set" if repo.lower() in skip else "DepTime's own repository"
            continue
        if repo.lower() in taken:
            entry["skipped"] = "this repository already gave this package a pull request"
            continue
        if full[stratum] >= PER_STRATUM:
            entry["skipped"] = f"{stratum} stratum full"
            continue
        try:
            if repo_info(repo).get("fork"):
                entry["skipped"] = "fork"
                continue
            pr = json.loads(gh("api", f"repos/{repo}/pulls/{it['number']}"))
            files = json.loads(gh("api", f"repos/{repo}/pulls/{it['number']}/files?per_page=100"))
        except RuntimeError as exc:
            entry["skipped"] = f"GitHub API: {exc}"[:200]
            continue
        manifests = sorted(f["filename"] for f in files if _MANIFEST.search(f["filename"]))
        if not manifests:
            entry["skipped"] = "changes no Python manifest"
            continue
        pdir = project_dir(it, ddir, manifests)
        entry["dir"] = pdir
        base_sha, head_sha = pr["base"]["sha"], pr["head"]["sha"]
        slug = repo.replace("/", "__")
        head_src = sources / f"{slug}@{head_sha}"
        base_src = sources / f"{slug}@{base_sha}"
        try:
            fetch_source(repo, head_sha, head_src, KEEP)
            fetch_source(repo, base_sha, base_src, KEEP)
        except Exception as exc:  # a tarball GitHub won't serve
            entry["skipped"] = f"source unavailable: {type(exc).__name__}"
            continue
        code_root = head_src / pdir if pdir else head_src
        if any(
            (code_root / p / r.replace(".", "/") / "__init__.py").exists() for p in ("", "src") for r in roots
        ):
            entry["skipped"] = "the package's own source"
            continue
        row = {
            "id": f"pr-{slug.lower()}-{it['number']}-{package}",
            "source": "pr",
            "bot": it["bot"],
            "repo": f"https://github.com/{repo}",
            "number": it["number"],
            "url": it["html_url"],
            "title": it["title"],
            "created_at": it["created_at"],
            "state": "merged" if pr.get("merged_at") else pr["state"],
            "base_commit": base_sha,
            "commit": head_sha,
            "dir": pdir,
            "manifests": manifests,
            "from": a,
            "to": b,
            "stratum": stratum,
            "python": "3.11",
        }
        built = upgrade(code_root, row, package) if code_root.is_dir() else None
        n = built["uses_found"] if built else 0
        if n < MIN_USES:
            entry["skipped"] = f"{n} uses"
            continue
        entry["kept"] = row["id"]
        kept.append(built)
        taken.add(repo.lower())
        full[stratum] += 1
    return kept


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("work", type=Path)
    ap.add_argument("--packages", default="", help="comma-separated; default every covered package")
    a = ap.parse_args()
    settings = Settings.from_env()
    store = open_index(settings.index_path)
    if store is None:
        print("no index; run `deptime index pull` first", file=sys.stderr)
        return 2
    a.work.mkdir(parents=True, exist_ok=True)
    sources = a.work / "sources"
    state_file = a.work / "selection.json"
    state = (
        json.loads(state_file.read_text(encoding="utf-8"))
        if state_file.exists()
        else {"index_built_at": store.built_at(), "done": [], "upgrades": [], "log": []}
    )
    skip = earlier_repos([HOLDOUT / s for s in SETS])
    packages = [canonicalize_name(p) for p in a.packages.split(",") if p] or sorted(COV)
    for package in packages:
        if package in state["done"]:
            continue
        indexed = {r["version"] for r in store.releases(COV[package].name)}
        log: list = []
        try:
            kept = candidates(package, indexed, skip, sources, log)
        except RuntimeError as exc:
            log.append({"package": package, "error": str(exc)[:300]})
            print(f"{package}: error, not marked done: {exc}", file=sys.stderr, flush=True)
            state["log"].extend(log)
            state_file.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
            continue
        state["upgrades"].extend(kept)
        state["log"].extend(log)
        state["done"].append(package)
        state_file.write_text(json.dumps(state, indent=1) + "\n", encoding="utf-8")
        strata = [u["stratum"] for u in kept]
        print(
            f"{package}: {strata.count('major')} major, {strata.count('other')} other ({len(log)} read)",
            file=sys.stderr,
            flush=True,
        )
    if set(sorted(COV)) - set(state["done"]):
        print("not every package is done; run again", file=sys.stderr)
        return 1
    selection = {
        "date": time.strftime("%Y-%m-%d"),
        "cutoff": CUTOFF,
        "index_built_at": state["index_built_at"],
        "window": [START, END],
        "search": BOTS,
        "per_stratum": PER_STRATUM,
        "min_uses": MIN_USES,
        "excluded": f"forks; DepTime's own repository; repositories in a holdout set: {', '.join(SETS)}",
        "kept": [u["id"] for u in state["upgrades"]],
        # Candidates passed over only because their stratum was already full are counted, not listed.
        "stratum_full": dict(
            sorted(
                Counter(
                    e["package"] for e in state["log"] if str(e.get("skipped")).endswith("stratum full")
                ).items()
            )
        ),
        "log": [
            {
                k: e[k]
                for k in ("package", "url", "from", "to", "stratum", "dir", "skipped", "kept", "error")
                if k in e
            }
            for e in state["log"]
            if not str(e.get("skipped")).endswith("stratum full")
        ],
    }
    head = json.dumps({k: v for k, v in selection.items() if k != "log"}, indent=1)[:-2]
    log = ",\n".join("  " + json.dumps(e) for e in selection["log"])
    (HERE / "selection.json").write_text(f'{head},\n "log": [\n{log}\n ]\n}}\n', encoding="utf-8")
    (HERE / "upgrades.jsonl").write_text(
        "".join(json.dumps(u) + "\n" for u in state["upgrades"]), encoding="utf-8"
    )
    print(f"{len(state['upgrades'])} pull requests -> {HERE / 'upgrades.jsonl'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
