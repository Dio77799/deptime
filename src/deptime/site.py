"""Rename-map pages generated from the index (DT-GTM-01): one static page per well-known migration, every row from
the same data the MCP tools serve, never written by hand.

  uv run python -m deptime.site build --out site/dist [--index PATH] [--base-url https://example.org]

Each page lists, between the newest release of the old series and the newest of the new one, the names and
arguments that went away and what the index says replaces them (the library's own text, a curated guide, or the same
object at another path), then the ones removed without a stated replacement. Library text is escaped and quoted as
data. Writes one page per migration, index.html (a short landing page for DepTime that lists them), llms.txt and,
with --base-url, sitemap.xml and each page's canonical URL. `.github/workflows/pages.yml` publishes them to GitHub
Pages after every index build (DT-GTM-02).
"""

from __future__ import annotations

import argparse
import builtins
import html
import sys
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from packaging.version import InvalidVersion, Version

from deptime.ingest.curated import hints_for
from deptime.models import HistoryEvent, Replacement
from deptime.query import EXPLAIN_MIN_CONFIDENCE, SEVERITY, DepTime

MAX_ROWS = 400  # per section, so a page stays readable
CHANGES = ("removed", "moved", "param_removed", "deprecated", "param_deprecated")
SOURCES = {
    "deprecation_message": "the library's deprecation text",
    "moved_heuristic": "the same object at another path",
    "curated": "the project's migration guide",
    "error_message": "the library's error message",
}


@dataclass(frozen=True)
class Range:
    package: str
    old: str  # version prefix of the old series, e.g. "1." or "0.3."
    new: str | None = None  # version prefix of the new series; None for the newest release


@dataclass(frozen=True)
class Migration:
    slug: str
    title: str
    ranges: tuple[Range, ...] = ()
    curated_from: str | None = None  # a distribution whose curated hints point into another one


MIGRATIONS = (
    Migration("mcp-1-to-2", "MCP Python SDK 1.x → 2.x", (Range("mcp", "1."),)),
    Migration(
        "langchain-0.3-to-1",
        "LangChain 0.3 → 1.x",
        (Range("langchain", "0.3."), Range("langchain-core", "0.3.")),
    ),
    Migration(
        "google-generativeai-to-google-genai",
        "google-generativeai → google-genai",
        curated_from="google-generativeai",
    ),
    Migration("pydantic-1-to-2", "pydantic v1 → v2", (Range("pydantic", "1.10.", "2."),)),
    Migration("openai-0-to-1", "openai 0.x → 1.x", (Range("openai", "0.28", "1."),)),
    Migration("httpx-0.27-to-0.28", "httpx 0.27 → 0.28", (Range("httpx", "0.27.", "0.28."),)),
)

STYLE = """
:root { --fg: #1f2328; --muted: #59636e; --bg: #ffffff; --line: #d1d9e0; --code: #f6f8fa; }
@media (prefers-color-scheme: dark) { :root { --fg: #e6edf3; --muted: #9198a1; --bg: #0d1117; --line: #3d444d; --code: #151b23; } }
body { margin: 0 auto; max-width: 64rem; padding: 1.5rem 1rem; font: 16px/1.5 system-ui, sans-serif; color: var(--fg); background: var(--bg); }
h1 { font-size: 1.6rem; } h2 { font-size: 1.2rem; margin-top: 2rem; }
p.meta, td.ev { color: var(--muted); font-size: 0.9rem; }
table { border-collapse: collapse; width: 100%; } th, td { text-align: left; vertical-align: top; padding: 0.35rem 0.5rem; border-bottom: 1px solid var(--line); }
code { background: var(--code); padding: 0 0.2rem; border-radius: 3px; overflow-wrap: anywhere; }
pre { background: var(--code); padding: 0.75rem 1rem; border-radius: 6px; overflow-x: auto; }
pre code { padding: 0; }
.cta { border: 1px solid var(--line); border-radius: 6px; padding: 0.25rem 1rem; margin: 1rem 0; }
a { color: inherit; }
"""

REPO = "https://github.com/cschmertz/deptime"
ACTION_DOCS = f"{REPO}/blob/main/docs/github-action.md"
BENCHMARK = f"{REPO}/blob/main/bench/README.md"
# Shown on every rename map: the reader came for one migration and is probably in the middle of it.
CTA = (
    '<div class="cta"><p><b>Updating your own code?</b> DepTime can point to each line a dependency update breaks. '
    "Update your lockfile or requirements, then run <code>uvx deptime check-upgrade</code>, or add the "
    f'<a href="{ACTION_DOCS}">GitHub Action</a> to check every update pull request. It runs on your machine, '
    f'with no AI model in the loop. <a href="{REPO}">DepTime on GitHub</a>.</p></div>'
)


def _newest(dt: DepTime, package: str, prefix: str | None) -> str | None:
    assert dt.store is not None
    versions = [r["version"] for r in dt.store.releases(package)]
    if prefix is not None:
        versions = [v for v in versions if v.startswith(prefix)]
    try:
        return max(versions, key=Version) if versions else None
    except InvalidVersion:
        return versions[-1] if versions else None


def _replacements(dt: DepTime, package: str, event: HistoryEvent) -> list[Replacement]:
    """The replacements the index states at confidence 0.75 or more, as `explanation` would, best first. A
    parameter's come from `symbol_history` as `func(param) -> new`."""
    history = dt.symbol_history(package, event.path)
    param = event.detail.get("param") if event.kind in {"param_removed", "param_deprecated"} else None
    found = []
    for r in history.replacements:
        if r.confidence < EXPLAIN_MIN_CONFIDENCE:
            continue
        if param is None and " -> " not in r.target:
            found.append(r)
        elif param is not None and r.target.startswith(f"{event.path}({param}) -> "):
            found.append(r.model_copy(update={"target": r.target.split(" -> ", 1)[1]}))
    return found


def _artefact(path: str) -> bool:
    """A path no one writes: a module seen through itself (`pydantic.v1.v1.BaseModel`, a re-export loop) or a
    builtin warning a module happens to import (`pydantic.config.DeprecationWarning`). A rename map lists neither.
    Only warnings: methods named `list` or `__init__`, and a library's own `ConnectionError`, are real API."""
    parts = path.split(".")
    builtin = getattr(builtins, parts[-1], None)
    warning = isinstance(builtin, type) and issubclass(builtin, Warning)
    return warning or any(a == b for a, b in pairwise(parts))


def _code(text: str) -> str:
    return f"<code>{html.escape(text)}</code>"


def _evidence(r: Replacement) -> str:
    text = (r.evidence or "")[:240]
    return (
        f"{html.escape(SOURCES.get(r.source, r.source))}: “{html.escape(text)}”"
        if text
        else html.escape(r.source)
    )


def _rows(dt: DepTime, rng: Range) -> tuple[str, list[str], list[str]]:
    assert dt.store is not None
    old, new = _newest(dt, rng.package, rng.old), _newest(dt, rng.package, rng.new)
    if old is None or new is None:
        return "", [], []
    lo, _ = dt.store.resolve_version(rng.package, old)
    hi, _ = dt.store.resolve_version(rng.package, new)
    if lo is None or hi is None:
        return "", [], []
    # Every event in the range, not the tool's 500 (`diff_versions`), from the same rows.
    rows, _ = dt.store.events_between(
        rng.package, lo["ordinal"], hi["ordinal"], 1_000_000, severity=SEVERITY, include_added=False
    )
    replaced, gone = [], []
    for e in (dt._event(rng.package, r) for r in rows):
        if e.kind not in CHANGES or _artefact(e.path):
            continue
        param = e.detail.get("param") if e.kind in {"param_removed", "param_deprecated"} else None
        name = f"{e.path}({param})" if param else e.path
        found = _replacements(dt, rng.package, e)
        if found:
            use = " or ".join(_code(r.target) for r in found)
            replaced.append(
                f"<tr><td>{_code(name)}</td><td>{use}</td><td>{html.escape(e.version)}</td>"
                f'<td class="ev">{_evidence(found[0])}</td></tr>'
            )
        elif e.kind == "removed" and e.path.count(".") <= 2:
            gone.append(f"<tr><td>{_code(name)}</td><td>{html.escape(e.version)}</td></tr>")
    return f"{rng.package} {old} → {new}", replaced[:MAX_ROWS], gone[:MAX_ROWS]


def _curated_rows(package: str) -> list[str]:
    return [
        f"<tr><td>{_code(h.path)}</td><td>{_code(h.target)}</td><td></td>"
        f'<td class="ev">{html.escape(SOURCES["curated"])}: “{html.escape(h.quote)}” '
        f'(<a href="{html.escape(h.url)}">source</a>)</td></tr>'
        for h in hints_for(package)
    ]


def _page(
    title: str, body: str, built: str | None, description: str = "", canonical: str | None = None
) -> str:
    head = f'<meta name="description" content="{html.escape(description)}">' if description else ""
    if canonical:
        head += f'<link rel="canonical" href="{html.escape(canonical)}">'
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title>{head}<style>{STYLE}</style></head><body>{body}"
        f'<p class="meta">Generated by DepTime from the index built {html.escape(built or "?")}. '
        f'Ask an agent the same through DepTime\'s MCP tools: <a href="{REPO}">'
        f"github.com/cschmertz/deptime</a>.</p></body></html>\n"
    )


def _landing(links: list[tuple[Migration, int, int]], packages: int) -> str:
    items = "".join(
        f'<li><a href="{m.slug}.html">{html.escape(m.title)}</a> ({n} replaced, {g} removed)</li>'
        for m, n, g in links
    )
    return (
        "<h1>DepTime</h1>"
        "<p><b>Know what a Python dependency update breaks before you merge it.</b> DepTime reads each release of "
        f"{packages} fast-moving Python libraries without running them, compares it with the release before, and points to "
        "each line of your code an update breaks, with what to use instead. No AI model in the loop: it runs "
        "offline, costs nothing, and gives the same answer every time.</p>"
        "<h2>Check an update</h2>"
        "<p>After updating your lockfile or requirements (you need "
        '<a href="https://docs.astral.sh/uv/">uv</a>):</p>'
        "<pre><code>uvx deptime check-upgrade</code></pre>"
        f'<p>Or add the <a href="{ACTION_DOCS}">GitHub Action</a> to check every Dependabot, Renovate or hand-made '
        "update pull request.</p>"
        "<h2>Give your coding agent the same answers</h2>"
        "<p>DepTime is also an MCP server for Claude Code, Cursor, VS Code, Codex and other agents:</p>"
        "<pre><code>claude mcp add deptime -- uvx deptime mcp</code></pre>"
        "<h2>Rename maps</h2>"
        "<p>Every name and argument these migrations renamed, moved or removed, and what replaces it, generated "
        f"from the same data:</p><ul>{items}</ul>"
        f'<p><a href="{REPO}">Source, docs and setup on GitHub</a> · '
        f'<a href="{BENCHMARK}">How it was measured</a> · Open source (MIT)</p>'
    )


def build(
    dt: DepTime, out: Path, migrations: tuple[Migration, ...] = MIGRATIONS, base_url: str | None = None
) -> list[Path]:
    assert dt.store is not None
    out.mkdir(parents=True, exist_ok=True)
    built = dt.store.built_at()
    base = base_url.rstrip("/") if base_url else None
    written, links = [], []
    for m in migrations:
        sections, spans = [], []
        replaced: list[str] = []
        gone: list[str] = []
        for rng in m.ranges:
            span, rows, removed = _rows(dt, rng)
            if span:
                spans.append(span)
                replaced += rows
                gone += removed
        if m.curated_from:
            replaced += _curated_rows(m.curated_from)
            spans.append(f"{m.curated_from} → its successor, from the projects' migration guides")
        head = "<tr><th>Old</th><th>Use instead</th><th>Changed in</th><th>Evidence</th></tr>"
        if replaced:
            sections.append(
                f"<h2>Renamed or replaced ({len(replaced)})</h2><table>{head}{''.join(replaced)}</table>"
            )
        if gone:
            sections.append(
                f"<h2>Removed, with no replacement stated ({len(gone)})</h2>"
                f"<table><tr><th>Old</th><th>Gone in</th></tr>{''.join(gone)}</table>"
            )
        intro = (
            f"<h1>{html.escape(m.title)}: what was renamed or removed</h1>"
            f'<p class="meta">{html.escape("; ".join(spans))}</p>'
            "<p>Every name and argument that went away in this migration, read from each release's own code, "
            "with what the library itself, its migration guide, or a move to another path says to use instead. "
            "Nothing here is written by hand.</p>"
            f"{CTA}"
        )
        description = (
            f"{m.title}: {len(replaced)} names and arguments renamed or replaced, {len(gone)} removed, and what "
            "to use instead, read from each release's own code."
        )
        page = _page(
            f"{m.title} migration: renamed and removed names",
            intro + "".join(sections),
            built,
            description,
            f"{base}/{m.slug}.html" if base else None,
        )
        path = out / f"{m.slug}.html"
        path.write_text(page, encoding="utf-8")
        written.append(path)
        links.append((m, len(replaced), len(gone)))
    (out / "index.html").write_text(
        _page(
            "DepTime: know what a Python dependency update breaks",
            _landing(links, len(dt.coverage.packages)),
            built,
            "Know what a Python dependency update breaks before you merge it: offline, free, no AI in the loop. "
            f"Plus rename maps: {', '.join(m.title for m, _, _ in links)}.",
            f"{base}/" if base else None,
        ),
        encoding="utf-8",
    )
    (out / "llms.txt").write_text(
        "# DepTime: Python API rename maps\n\n"
        "> Know what a Python dependency update breaks before you merge it. Each map lists the names and "
        "arguments a migration renamed or removed, and what replaces them, read from the releases' own code.\n\n"
        + "".join(f"- [{m.title}]({m.slug}.html): {n} names replaced, {g} removed\n" for m, n, g in links),
        encoding="utf-8",
    )
    written += [out / "index.html", out / "llms.txt"]
    if base:
        urls = "".join(
            f"<url><loc>{html.escape(f'{base}/{p.name}')}</loc></url>" for p in written if p.suffix == ".html"
        )
        (out / "sitemap.xml").write_text(
            f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n',
            encoding="utf-8",
        )
        written.append(out / "sitemap.xml")
    return written


def main(argv: list[str] | None = None) -> int:
    from deptime.config import Settings, load_coverage
    from deptime.index.location import active_index
    from deptime.index.store import IndexStore

    ap = argparse.ArgumentParser(prog="python -m deptime.site")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--out", type=Path, default=Path("site/dist"))
    b.add_argument("--index", type=Path)
    b.add_argument("--base-url")
    args = ap.parse_args(argv)
    index = args.index or active_index(Settings.from_env().index_path)
    if not index.is_file():
        print(f"no index at {index}: run `deptime index pull` first", file=sys.stderr)
        return 1
    for path in build(DepTime(IndexStore.open(index), load_coverage()), args.out, base_url=args.base_url):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
