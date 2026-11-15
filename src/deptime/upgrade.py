"""`deptime check-upgrade`: what a dependency update breaks in a project's code (DT-CORE-58, DT-CORE-59).

Every Python file in the project is read with DepTime's own reader (`snippet.py`; never the benchmark's independent
`bench/holdout/uses.py`), never imported or run. For each covered package whose version changes, its uses are checked
with `check_symbols` at the new version, and flagged as the holdout scorer counts a flag (`bench/holdout/score.py`): a
name missing, a keyword not accepted, a required argument not passed, more arguments by position than it takes, or a
call to a callable that only raises. A flag the old version also shows isn't caused by the update, so it is listed
apart (`failing_before`), as are uses DepTime can't tell about (`unknown`), and neither fails the check. No model is
asked anything (ADR 0006): the answer is the index's.
"""

from __future__ import annotations

import os
import subprocess
import warnings
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from packaging.utils import canonicalize_name

from deptime import snippet
from deptime.models import (
    CheckSymbolsResult,
    DependencyChange,
    Finding,
    PackageUpgrade,
    SymbolCheck,
    SymbolQuery,
    UpgradeBreak,
    UpgradeCheckResult,
    UpgradeNotice,
    UseLocation,
)
from deptime.untrusted import untrusted_text

MAX_FILE_BYTES = 2_000_000  # a larger .py file is generated data, not code someone maintains
MAX_UNREADABLE_LISTED = 20
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    "site-packages",
    "__pycache__",
    "build",
    "dist",
    ".eggs",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

Key = str | tuple[str, str]


# ------------------------------------------------------------------------------------------------- reading the code
def project_files(root: Path) -> list[str]:
    """The project's Python files, relative to `root`: what git tracks or would track (so `.gitignore` applies), else
    a walk that leaves out virtual environments, build output and caches."""
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--others",
                "--exclude-standard",
                "--",
                "*.py",
            ],
            capture_output=True,
            check=True,
        )
        files = [f for f in out.stdout.decode("utf-8", "replace").split("\0") if f]
        return sorted(f for f in files if (root / f).is_file() and not SKIP_DIRS & set(Path(f).parts[:-1]))
    except (OSError, subprocess.CalledProcessError):
        pass
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in filenames:
            if name.endswith(".py"):
                found.append((Path(dirpath) / name).relative_to(root).as_posix())
    return sorted(found)


def read_code(root: Path, files: Iterable[str]) -> dict[str, str]:
    code = {}
    for rel in files:
        path = root / rel
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            code[rel] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return code


def uses_in(text: str, roots: tuple[str, ...]) -> snippet.Uses | None:
    """A project file's uses, read whole; the warnings Python prints about other people's code (an invalid escape
    sequence) stay quiet."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return snippet.uses_in(text, roots, limit=None)


def own_modules(files: Iterable[str]) -> set[str]:
    """Top-level module names the project defines itself (`x.py`, `x/__init__.py`, `src/x/...`): an import of one is
    the project's own code, even when a covered package has the same name."""
    out = set()
    for rel in files:
        parts = rel.split("/")
        if parts[0] == "src" and len(parts) > 1:
            parts = parts[1:]
        if len(parts) == 1:
            out.add(parts[0].removesuffix(".py"))
        elif parts[-1] == "__init__.py" and len(parts) == 2:
            out.add(parts[0])
    return out


@dataclass
class _Read:
    """One package's uses across the project, with where each happens."""

    uses: snippet.Uses = field(default_factory=snippet.Uses)
    at: dict[Key, list[UseLocation]] = field(default_factory=dict)
    kwarg_at: dict[tuple[Key, str], list[UseLocation]] = field(default_factory=dict)
    call_at: dict[Key, list[UseLocation]] = field(default_factory=dict)
    files: set[str] = field(default_factory=set)

    def merge(self, rel: str, found: snippet.Uses) -> None:
        total = self.uses
        for path, kwargs in found.paths.items():
            total.add(path, kwargs)
        for (built_by, name), kwargs in found.members.items():
            total.add_member(built_by, name, kwargs)
        for key, count in found.positional.items():
            # A call that spreads `*args` or `**kwargs` may cover any parameter, in this file or an earlier one.
            if count is None or (key in total.positional and total.positional[key] is None):
                total.positional[key] = None
            else:
                total.positional[key] = max(total.positional.get(key) or 0, count or 0)
        for src, dst in ((found.lines, self.at), (found.call_lines, self.call_at)):
            for key, lines in src.items():
                dst.setdefault(key, []).extend(UseLocation(file=rel, line=n) for n in lines)
        for key, lines in found.kwarg_lines.items():
            self.kwarg_at.setdefault(key, []).extend(UseLocation(file=rel, line=n) for n in lines)
        if found.paths or found.members:
            self.files.add(rel)


def _keys(path: str, uses: snippet.Uses) -> list[Key]:
    """The reader's keys a checked path came from: the path itself, and members read off an object a call to a class
    built (`client.get` is `httpx.Client.get`)."""
    owner, _, attr = path.rpartition(".")
    keys: list[Key] = [path]
    if (owner, attr) in uses.members:
        keys.append((owner, attr))
    return keys


def _locations(table: dict, keys: list) -> list[UseLocation]:
    seen: dict[tuple[str, int], UseLocation] = {}
    for key in keys:
        for loc in table.get(key, []):
            seen.setdefault((loc.file, loc.line), loc)
    return sorted(seen.values(), key=lambda loc: (loc.file, loc.line))


# ----------------------------------------------------------------------------------------------------- the check
def _flags(r: SymbolCheck, called: bool) -> list[tuple[str, str | None]]:
    """What check_symbols' answer flags, by `bench/holdout/score.py`'s rule: (kind, keyword)."""
    if r.status != "present" and r.status != "missing":
        return []
    if r.status == "missing":
        return [("missing", None)]
    out: list[tuple[str, str | None]] = [("rejected_kwarg", k) for k in r.rejected_kwargs]
    if r.missing_args:
        out.append(("missing_args", None))
    if called and r.raises:
        out.append(("raises", None))
    if called and r.max_positional is not None:
        out.append(("too_many_positional", None))
    return out


def _explain(kind: str, kwarg: str | None, r: SymbolCheck, at: str) -> str:
    if kind == "missing":
        return f"`{r.path}` is missing at {at}" + (f" ({r.hint})" if r.hint else "") + "."
    if kind == "rejected_kwarg":
        return f"`{r.path}` doesn't take the keyword `{kwarg}` at {at}."
    if kind == "missing_args":
        args = ", ".join(f"`{a}`" for a in r.missing_args)
        return f"`{r.path}` requires {args} at {at}, which the calls don't pass."
    if kind == "raises":
        return f"`{r.path}` does nothing but raise at {at}: {untrusted_text(r.raises)}"
    return f"`{r.path}` {r.hint}." if r.hint else f"`{r.path}` takes fewer arguments by position at {at}."


def check_upgrade(
    dt,  # deptime.query.DepTime
    project: str,
    code: dict[str, str],
    changes: list[DependencyChange],
    base: str | None = None,
) -> UpgradeCheckResult:
    """Check each change against the project's code (`code`: relative path -> source)."""
    result = UpgradeCheckResult(project=project, base=base)
    own = own_modules(code)
    unreadable: set[str] = set()
    suppressed = 0
    for change in changes:
        name = canonicalize_name(change.package)
        if change.from_version is None or change.to_version is None:
            result.skipped.append(change)
            continue
        if dt.coverage.get(name) is None or not dt._indexed(name):
            result.not_covered.append(change)
            continue
        spec = dt._spec(name)
        roots = tuple(r for r in spec.import_names if r.split(".")[0] not in own)
        if not roots:
            result.checked.append(
                PackageUpgrade(
                    change=change,
                    resolved_version=None,
                    exact=False,
                    uses=0,
                    files=0,
                    note=f"The project defines its own `{spec.import_names[0].split('.')[0]}` module, so its imports"
                    f" of that name are its own code and nothing of {name} was read.",
                )
            )
            continue
        read = _Read()
        for rel, text in code.items():
            found = uses_in(text, roots)
            if found is None:
                unreadable.add(rel)
                continue
            read.merge(rel, found)
        upgrade, hidden = _check_package(dt, spec, change, read)
        suppressed += hidden
        result.checked.append(upgrade)
    result.breaks = sum(len(p.breaks) for p in result.checked)
    result.files_read = len(code) - len(unreadable)
    result.files_unreadable = sorted(unreadable)[:MAX_UNREADABLE_LISTED]
    result.suppressed = suppressed
    notes = []
    if unreadable:
        notes.append(
            f"{len(unreadable)} Python file{'' if len(unreadable) == 1 else 's'} didn't parse, so nothing was read"
            " from them."
        )
    if suppressed:
        notes.append(
            f"{suppressed} break{'' if suppressed == 1 else 's'} or notice{'' if suppressed == 1 else 's'} left out by"
            " this project's suppressions (deptime.toml or pyproject.toml)."
        )
    result.note = " ".join(notes) or None
    return result


def _results(dt, name: str, spec, version: str, queries: list[SymbolQuery]) -> CheckSymbolsResult:
    return dt._check_symbols(name, spec, version, queries)


def _check_package(dt, spec, change: DependencyChange, read: _Read) -> tuple[PackageUpgrade, int]:
    name, to, before = spec.name, change.to_version, change.from_version
    queries, count = dt._code_queries(name, to, [], read.uses)
    at_to = _results(dt, name, spec, to, queries)
    upgrade = PackageUpgrade(
        change=change,
        resolved_version=at_to.resolved_version,
        exact=at_to.exact,
        uses=count,
        files=len(read.files),
        note=at_to.note,
    )
    if at_to.resolved_version is None or not queries:
        return upgrade, 0
    from_row = dt.store.resolve_version(name, before)[0] if before else None
    at_from = _results(dt, name, spec, before, queries) if from_row is not None else None
    if at_from is None and before:
        extra = f"{before} is older than the earliest indexed release, so uses that fail there too aren't set apart."
        upgrade.note = " ".join(n for n in (upgrade.note, extra) if n)
    row, exact = dt.store.resolve_version(name, to)
    hidden = 0
    called_keys = set(read.call_at)
    for i, (q, r) in enumerate(zip(queries, at_to.results, strict=True)):
        keys = _keys(q.path, read.uses)
        called = any(k in called_keys for k in keys)
        where = _locations(read.at, keys)
        if r.status in ("unknown", "not_indexed"):
            upgrade.notices.append(
                UpgradeNotice(path=r.path, status="unknown", detail=r.hint or r.status, locations=where)
            )
            continue
        before_r = at_from.results[i] if at_from is not None else None
        before_flags = (
            set(_flags(before_r, called))
            if before_r is not None and before_r.status in ("present", "missing")
            else set()
        )
        flags = _flags(r, called)
        for kind, kwarg in flags:
            if kind == "rejected_kwarg":
                locs = _locations(read.kwarg_at, [(k, kwarg) for k in keys])
            elif kind in ("missing_args", "too_many_positional", "raises"):
                locs = _locations(read.call_at, keys) or where
            else:
                locs = where
            explanation = _explain(kind, kwarg, r, at_to.resolved_version)
            if (kind, kwarg) in before_flags:
                upgrade.notices.append(
                    UpgradeNotice(
                        path=r.path,
                        status="failing_before",
                        detail=f"Flagged at {before} too: {explanation}",
                        locations=locs,
                    )
                )
                continue
            finding = _finding(dt, spec, kind, kwarg, r, row, exact, to)
            issue = finding.issue if finding else kind
            symbol = finding.symbol if finding else r.path
            if any(s.matches(name, symbol, issue) for s in dt.suppressions):
                hidden += 1
                continue
            upgrade.breaks.append(
                UpgradeBreak(
                    path=r.path,
                    kind=kind,
                    kwarg=kwarg,
                    missing_args=r.missing_args if kind == "missing_args" else [],
                    explanation=explanation,
                    locations=locs,
                    finding=finding,
                    internal=r.internal,
                )
            )
        if not flags and r.deprecated:
            if any(s.matches(name, r.path, "deprecated") for s in dt.suppressions):
                hidden += 1
                continue
            since, _ = dt._deprecation(name, r.path)
            upgrade.notices.append(
                UpgradeNotice(
                    path=r.path,
                    status="deprecated",
                    detail=r.deprecated,
                    new=not (before_r is not None and before_r.deprecated),
                    deprecated_in=since,
                    locations=where,
                )
            )
    return upgrade, hidden


def _finding(
    dt, spec, kind: str, kwarg: str | None, r: SymbolCheck, row, exact: bool, to: str
) -> Finding | None:
    """The change as explain_error describes it, with the release, the replacements and a proven fix."""
    name = spec.name
    if kind == "missing":
        f = dt._symbol_finding(spec, r.path, row, exact, to)
    elif kind in ("rejected_kwarg", "missing_args"):
        param = kwarg if kind == "rejected_kwarg" else r.missing_args[0]
        signal = "unexpected_kwarg" if kind == "rejected_kwarg" else "missing_argument"
        f = dt._param_finding(spec, dt._constructor(name, r.path), param, signal, row, exact, to)
    else:
        return None
    return dt._act_on(f, {name: to}) if f is not None else None


# ------------------------------------------------------------------------------------------------------ the report
MAX_LOCATIONS_SHOWN = 5


def _md(text: str | None) -> str:
    """Text for a Markdown report: library text is untrusted, so nothing in it renders as markup."""
    if not text:
        return ""
    out = []
    for c in text:
        out.append("\\" + c if c in "\\`*_[]<>|#!~" else c)
    return "".join(out)


def _code(text: str) -> str:
    return "`" + text.replace("`", "'") + "`"


def _where(locs: list[UseLocation]) -> str:
    shown = ", ".join(_code(f"{loc.file}:{loc.line}") for loc in locs[:MAX_LOCATIONS_SHOWN])
    more = len(locs) - MAX_LOCATIONS_SHOWN
    return shown + (f" and {more} more" if more > 0 else "")


def _break_line(b: UpgradeBreak, at: str) -> str:
    use = _code(f"{b.path}({b.kwarg}=)" if b.kind == "rejected_kwarg" else b.path)
    reason = {
        "missing": f"missing at {at}",
        "rejected_kwarg": f"the keyword isn't accepted at {at}",
        "missing_args": f"requires {', '.join(_code(a) for a in b.missing_args)} at {at}, which the calls don't pass",
    }.get(b.kind) or _md(b.explanation.replace("`", ""))
    parts = [f"- {use}: {reason}."]
    f = b.finding
    if f is not None:
        if f.first_version_without and f.last_version_with:
            parts.append(f"Last in {f.last_version_with}, gone in {f.first_version_without}.")
        elif f.first_version_with and f.last_version_without:
            parts.append(f"Added in {f.first_version_with}.")
        if f.fix is not None:
            parts.append(f"Fix: {_code(f.fix.old)} → {_code(f.fix.new)} ({f.fix.source}).")
        elif f.replacements:
            r = f.replacements[0]
            parts.append(f"Try {_code(r.target)} ({r.source}, confidence {r.confidence:.2f}).")
    elif b.kind == "missing" and "; try " in b.explanation:
        parts.append(f"Try {_code(b.explanation.split('; try ', 1)[1].rstrip(').'))}.")
    if b.locations:
        parts.append(f"At {_where(b.locations)}.")
    return " ".join(parts)


def to_markdown(result: UpgradeCheckResult) -> str:
    lines = ["## DepTime upgrade check", ""]
    n = result.breaks
    checked = ", ".join(
        f"{p.change.package} {p.change.from_version} → {p.change.to_version}" for p in result.checked
    )
    if not result.checked:
        lines.append("No covered package's version changed, so nothing was checked.")
    elif n:
        lines.append(f"**{n} break{'' if n == 1 else 's'} found** in this project's code: {checked}.")
    else:
        lines.append(f"**No breaks found** in this project's code: {checked}.")
    lines.append("")
    for p in result.checked:
        c = p.change
        head = f"### {c.package} {c.from_version} → {c.to_version}"
        lines += [head, ""]
        facts = [
            f"{p.uses} name{'' if p.uses == 1 else 's'} used in {p.files} file{'' if p.files == 1 else 's'}"
        ]
        if c.source:
            facts.append(f"read from {_code(c.source)}")
        if p.resolved_version and not p.exact:
            facts.append(f"answered for {p.resolved_version}, the nearest indexed release")
        lines += ["; ".join(facts) + ".", ""]
        if p.breaks:
            lines.append("**Breaks**")
            lines += [_break_line(b, p.resolved_version or c.to_version or "") for b in p.breaks]
            lines.append("")
        groups = [
            ("deprecated", "Deprecated at the new version", lambda x: x.new, True),
            ("deprecated", "Already deprecated at the old version", lambda x: not x.new, False),
            (
                "failing_before",
                "Flagged at the old version too, so not caused by this update",
                lambda x: True,
                False,
            ),
            ("unknown", "DepTime can't tell (never fails the check)", lambda x: True, False),
        ]
        for status, title, keep, shown in groups:
            items = [x for x in p.notices if x.status == status and keep(x)]
            if not items:
                continue
            lines.append(f"**{title}**" if shown else f"<details><summary>{title}: {len(items)}</summary>\n")
            for x in items:
                since = f" (since {x.deprecated_in})" if x.deprecated_in else ""
                at = f" At {_where(x.locations)}." if x.locations else ""
                lines.append(f"- {_code(x.path)}{since}: {_md(x.detail)}{at}")
            lines += [""] if shown else ["", "</details>", ""]
        if p.note:
            lines += [_md(p.note), ""]
    if result.not_covered:
        names = ", ".join(f"{c.package} {c.from_version} → {c.to_version}" for c in result.not_covered)
        lines += [f"Not covered by DepTime's index, so not checked: {_md(names)}.", ""]
    if result.note:
        lines += [_md(result.note), ""]
    lines.append(
        "DepTime reads the code and the index; it runs nothing and asks no model. A break is a use the index shows"
        " failing at the new version and not at the old one."
    )
    return "\n".join(lines) + "\n"
