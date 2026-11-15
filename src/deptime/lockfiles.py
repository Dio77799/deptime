"""The packages and versions a project pins, and what changed between two revisions of its files (DT-CORE-66).

Read as text, never installed or imported (Invariant 1). A project's pins come from, in this order:

- `uv.lock` or `poetry.lock`: the resolved version of every package (`[[package]]` tables);
- `requirements*.txt` (at the root and under `requirements/`), following `-r` includes inside the project: lines
  that pin one version with `==` (or `===`);
- `pyproject.toml`: `[project]` dependencies, optional dependencies and `[dependency-groups]` pinned with `==`, and
  Poetry's dependencies written as an exact version (`"1.2.3"`, `"==1.2.3"`, `{version = "1.2.3"}`).

A file is read at a git revision with `git show REV:path`, so a pull request's base and head can be compared without
checking either out. A range (`>=1.2`) is not a pin and is skipped: the version it resolves to is unknown.
"""

from __future__ import annotations

import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

LOCKFILES = ("uv.lock", "poetry.lock")
MAX_INCLUDES = 20  # `-r` files followed from one requirements file
_REQ_GLOBS = ("requirements*.txt", "requirements/*.txt", "requirements/**/*.txt")
_POETRY_EXACT = re.compile(r"^\s*(?:==\s*)?v?(\d[\w.!+-]*)\s*$")


@dataclass(frozen=True)
class Pin:
    package: str  # canonical distribution name
    version: str
    source: str  # the file it was read from, relative to the project


@dataclass(frozen=True)
class Change:
    package: str
    from_version: str | None  # None: added at head
    to_version: str | None  # None: removed at head
    source: str


@dataclass
class Pins:
    """Every pin a project's files give, by file (a package may be pinned in several)."""

    by_file: dict[str, dict[str, str]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)  # files that couldn't be read, with the reason

    def versions(self, package: str) -> dict[str, str]:
        """file -> the version it pins `package` at."""
        name = canonicalize_name(package)
        return {f: pins[name] for f, pins in self.by_file.items() if name in pins}

    def all(self) -> list[Pin]:
        return [Pin(p, v, f) for f, pins in self.by_file.items() for p, v in sorted(pins.items())]


class Tree:
    """A project's files: the working tree, or a git revision of it (`git show`)."""

    def __init__(self, root: Path, rev: str | None = None) -> None:
        self.root = root
        self.rev = rev
        self._listing: list[str] | None = None

    def _git(self, *args: str) -> str:
        out = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if out.returncode != 0:
            raise OSError(out.stderr.strip() or f"git {' '.join(args)} failed")
        return out.stdout

    def files(self) -> list[str]:
        """Paths relative to the project root, POSIX style."""
        if self._listing is None:
            if self.rev is None:
                self._listing = sorted(
                    p.relative_to(self.root).as_posix()
                    for g in ("*", "requirements/**/*")
                    for p in self.root.glob(g)
                    if p.is_file()
                )
            else:
                # Paths relative to the project directory, which may be a subdirectory of the repository.
                out = self._git("ls-tree", "-r", "--name-only", "--full-tree", self.rev, "--", ".")
                prefix = self._git("rev-parse", "--show-prefix").strip()
                self._listing = sorted(
                    line.removeprefix(prefix) for line in out.splitlines() if line.startswith(prefix)
                )
        return self._listing

    def read(self, rel: str) -> str | None:
        if self.rev is None:
            path = self.root / rel
            return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else None
        if rel not in self.files():
            return None
        return self._git("show", f"{self.rev}:./{rel}")


def _version(raw: str) -> str | None:
    try:
        return str(Version(raw))
    except InvalidVersion:
        return None


def _lock_pins(text: str) -> dict[str, str]:
    data = tomllib.loads(text)
    out = {}
    for pkg in data.get("package", []):
        if not isinstance(pkg, dict) or not isinstance(pkg.get("name"), str):
            continue
        if isinstance(pkg.get("version"), str) and (v := _version(pkg["version"])) is not None:
            out[canonicalize_name(pkg["name"])] = v
    return out


def _requirement_pin(line: str) -> tuple[str, str] | None:
    """`name==1.2.3` (extras and markers allowed) as (canonical name, version); None for anything else."""
    try:
        req = Requirement(line)
    except InvalidRequirement:
        return None
    if req.url:
        return None
    specs = list(req.specifier)
    if len(specs) != 1 or specs[0].operator not in ("==", "===") or "*" in specs[0].version:
        return None
    v = _version(specs[0].version)
    return (canonicalize_name(req.name), v) if v else None


def _requirements(tree: Tree, rel: str, seen: set[str]) -> dict[str, str]:
    if rel in seen or len(seen) > MAX_INCLUDES:
        return {}
    seen.add(rel)
    text = tree.read(rel)
    if text is None:
        return {}
    out: dict[str, str] = {}
    joined = re.sub(r"\\\r?\n", " ", text)  # line continuations
    for raw in joined.splitlines():
        line = re.sub(r"(^|\s)#.*$", "", raw).strip()
        if not line:
            continue
        if m := re.match(r"^(?:-r|--requirement)(?:\s+|=)(\S+)", line):
            inc = PurePosixPath(rel).parent / m.group(1)
            parts: list[str] = []
            for part in inc.parts:  # stay inside the project
                if part == "..":
                    if not parts:
                        break
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            else:
                out.update(
                    {k: v for k, v in _requirements(tree, "/".join(parts), seen).items() if k not in out}
                )
            continue
        if line.startswith("-"):
            continue
        line = re.split(r"\s+--?\w", line, maxsplit=1)[0]  # `--hash=...` and other per-line options
        if (pin := _requirement_pin(line)) is not None:
            out[pin[0]] = pin[1]
    return out


def _pyproject_pins(text: str) -> dict[str, str]:
    data = tomllib.loads(text)
    lines: list[str] = []
    project = data.get("project", {})
    lines += project.get("dependencies", []) or []
    for group in (project.get("optional-dependencies", {}) or {}).values():
        lines += group or []
    for group in (data.get("dependency-groups", {}) or {}).values():
        lines += [x for x in group or [] if isinstance(x, str)]
    out: dict[str, str] = {}
    for line in lines:
        if isinstance(line, str) and (pin := _requirement_pin(line)) is not None:
            out.setdefault(*pin)
    poetry = data.get("tool", {}).get("poetry", {})
    tables = [poetry.get("dependencies", {}), poetry.get("dev-dependencies", {})]
    tables += [
        g.get("dependencies", {}) for g in (poetry.get("group", {}) or {}).values() if isinstance(g, dict)
    ]
    for table in tables:
        for name, spec in (table or {}).items():
            if canonicalize_name(name) == "python":
                continue
            raw = spec.get("version") if isinstance(spec, dict) else spec
            if isinstance(raw, str) and (m := _POETRY_EXACT.match(raw)) and (v := _version(m.group(1))):
                out.setdefault(canonicalize_name(name), v)
    return out


def read_pins(root: Path, rev: str | None = None) -> Pins:
    """Every pin the project's files give, from the working tree or a git revision."""
    tree = Tree(root, rev)
    pins = Pins()
    files = tree.files()
    for lock in LOCKFILES:
        if lock in files:
            try:
                pins.by_file[lock] = _lock_pins(tree.read(lock) or "")
            except (tomllib.TOMLDecodeError, OSError) as exc:
                pins.problems.append(f"{lock}: {type(exc).__name__}: {exc}")
    reqs = sorted(
        {f for f in files for g in _REQ_GLOBS if PurePosixPath(f).match(g)},
        key=lambda f: (f.count("/"), f),
    )
    for rel in reqs:
        try:
            found = _requirements(tree, rel, set())
        except OSError as exc:
            pins.problems.append(f"{rel}: {type(exc).__name__}: {exc}")
            continue
        if found:
            pins.by_file[rel] = found
    if "pyproject.toml" in files:
        try:
            found = _pyproject_pins(tree.read("pyproject.toml") or "")
        except (tomllib.TOMLDecodeError, OSError) as exc:
            pins.problems.append(f"pyproject.toml: {type(exc).__name__}: {exc}")
        else:
            if found:
                pins.by_file["pyproject.toml"] = found
    return pins


def project_name(root: Path) -> str | None:
    """The project's own distribution name (`[project]` or `[tool.poetry]` in pyproject.toml): a lockfile lists it,
    and its version changing is no dependency update."""
    try:
        data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None
    name = data.get("project", {}).get("name") or data.get("tool", {}).get("poetry", {}).get("name")
    return canonicalize_name(name) if isinstance(name, str) else None


def changes(base: Pins, head: Pins, packages: set[str] | None = None) -> list[Change]:
    """Each package whose pinned version a file changes between `base` and `head`, once per (package, from, to).
    A package added or removed at head is listed with None on that side."""
    out: dict[tuple[str, str | None, str | None], Change] = {}
    for rel in sorted(set(base.by_file) | set(head.by_file)):
        before, after = base.by_file.get(rel, {}), head.by_file.get(rel, {})
        for name in sorted(set(before) | set(after)):
            if packages is not None and name not in packages:
                continue
            a, b = before.get(name), after.get(name)
            if a != b:
                out.setdefault((name, a, b), Change(name, a, b, rel))
    return list(out.values())
