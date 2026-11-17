"""Draw the README's demos from real answers (DT-OSS-02, DT-GTM-10): docs/assets/demo-*.svg and upgrade-*.svg.

    uv run python tools/demo_svg.py

`demo-*`: runs `deptime explain` on the README's error against the local index (`deptime index pull` first) and
draws the command and its answer, trimmed to the fields the README shows, as an animated terminal.

`upgrade-*`: builds a two-file project in a temporary git repository, commits it, updates two pins in its
requirements.txt, and draws `git diff` and `deptime check-upgrade` as the terminal shows them, with the Markdown
markers rendered and the agent block and footer trimmed, then the exit code.

No value in the pictures is typed by hand: when an answer changes, so do the pictures.

The animation is CSS inside the SVG, which plays where the file is shown as an image (GitHub, PyPI). Every element is
visible unless its animation hides it, so without animation, or with reduced motion, the last frame shows.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from html import escape
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"

ERROR = "TypeError: Client.__init__() got an unexpected keyword argument 'proxies'"
INSTALLED = "httpx==0.28.1"
ERROR_FILE = "error.txt"
SHOW = f"cat {ERROR_FILE}"
EXPLAIN = f"deptime explain --installed {INSTALLED} < {ERROR_FILE}"

# The fields of the finding the README's example keeps, in its order.
FIELDS = (
    "symbol",
    "issue",
    "installed_version",
    "last_version_with",
    "first_version_without",
    "deprecated_in",
    "replacements",
    "pin_to_restore",
    "confidence",
)
REPLACEMENT_FIELDS = ("target", "confidence", "source")
# The values that say what changed, in which release, and what to use instead.
EMPHASIZED = {"issue", "last_version_with", "first_version_without", "target", "pin_to_restore"}

WIDTH = 760
PAD_X = 24
BAR = 36  # the window's title bar
FIRST_BASELINE = BAR + 30
LINE = 20
FONT = "ui-monospace,SFMono-Regular,'SF Mono',Menlo,Consolas,'Liberation Mono',monospace"

LOOP = 13.0  # seconds
FADE_OUT = (95.0, 97.0)  # percent of the loop: everything fades, and the terminal is empty until it ends
TYPE_SHOW = (0.4, 0.05)  # start (s), seconds per character
ERROR_AT = 1.35
PROMPT_AT = 1.9
TYPE_EXPLAIN = (2.3, 0.04)
ANSWER_AT, ANSWER_STEP = 4.9, 0.09
LINE_FADE = 0.15  # seconds an output line takes to appear


@dataclass(frozen=True)
class Theme:
    name: str
    window: str
    border: str
    bar: str
    text: str
    muted: str
    error: str
    key: str
    emphasis: str
    added: str


LIGHT = Theme(
    "light", "#F6F8FA", "#D1D9E0", "#EAEEF2", "#1F2328", "#59636E", "#CF222E", "#306998", "#9A6700", "#1A7F37"
)
DARK = Theme(
    "dark", "#161B22", "#30363D", "#0D1117", "#E6EDF3", "#9198A1", "#FF7B72", "#739FC4", "#FFD43B", "#3FB950"
)

Span = tuple[str, str]  # (class, text)


def answer() -> dict:
    """The first finding `deptime explain` gives for the README's error."""
    run = subprocess.run(
        ["deptime", "explain", "--installed", INSTALLED],
        input=ERROR + "\n",
        capture_output=True,
        text=True,
        check=True,
    )
    findings = json.loads(run.stdout)["findings"]
    if not findings:
        sys.exit("deptime explain returned no finding: is the index pulled (`deptime index pull`)?")
    return findings[0]


def _pair(key: str, value: object) -> list[Span]:
    cls = "e" if key in EMPHASIZED else "t"
    return [("k", json.dumps(key)), ("p", ": "), (cls, json.dumps(value))]


def answer_lines(finding: dict) -> list[list[Span]]:
    """The trimmed finding as pretty-printed JSON, one list of coloured spans per line."""
    lines: list[list[Span]] = [[("p", "{")]]
    for n, field in enumerate(FIELDS):
        comma = [("p", ",")] if n < len(FIELDS) - 1 else []
        if field != "replacements":
            lines.append([("p", "  "), *_pair(field, finding[field]), *comma])
            continue
        lines.append([("p", "  "), ("k", json.dumps(field)), ("p", ": [")])
        replacements = finding[field]
        for m, replacement in enumerate(replacements):
            spans: list[Span] = [("p", "    {")]
            for i, key in enumerate(REPLACEMENT_FIELDS):
                spans += [("p", ", ")] if i else []
                spans += _pair(key, replacement[key])
            spans.append(("p", "}," if m < len(replacements) - 1 else "}"))
            lines.append(spans)
        lines.append([("p", "  ]"), *comma])
    lines.append([("p", "}")])
    return lines


class Reveals:
    """One CSS animation per moment something appears, all on the same loop."""

    def __init__(self) -> None:
        self.rules: list[str] = []

    def at(self, seconds: float, fade: float = 0.0) -> str:
        """The class of an element that appears at `seconds`, over `fade` seconds, and leaves with the rest."""
        name = f"r{len(self.rules)}"
        hidden_until = 100 * seconds / LOOP
        shown_from = hidden_until + max(100 * fade / LOOP, 0.01)
        out_from, out_to = FADE_OUT
        self.rules.append(
            f"@keyframes {name}{{0%,{hidden_until:.2f}%{{opacity:0}}{shown_from:.2f}%,{out_from}%{{opacity:1}}"
            f"{out_to}%,100%{{opacity:0}}}}.{name}{{animation-name:{name}}}"
        )
        return name


def _spans(spans: list[Span]) -> str:
    return "".join(f'<tspan class="{cls}">{escape(text, quote=False)}</tspan>' for cls, text in spans)


def _typed(command: str, start: float, per_char: float, reveals: Reveals) -> tuple[str, float]:
    """`command` as one tspan per character, each appearing in turn, and the time the last one does."""
    out = []
    for i, char in enumerate(command):
        out.append(f'<tspan class="a {reveals.at(start + i * per_char)}">{escape(char, quote=False)}</tspan>')
    return "".join(out), start + len(command) * per_char


class Terminal:
    """Rows of a terminal window, each appearing at its moment of the loop."""

    def __init__(self) -> None:
        self.reveals = Reveals()
        self.rows: list[str] = []

    def row(self, body: str, cls: str = "") -> None:
        y = FIRST_BASELINE + LINE * len(self.rows)
        self.rows.append(f'<text x="{PAD_X}" y="{y}"{f' class="{cls}"' if cls else ""}>{body}</text>')

    def window(self, theme: Theme, cursor_at: float, label: str, bar: str) -> str:
        """The finished SVG: a prompt and a blinking cursor at `cursor_at` seconds below the last row."""
        reveals = self.reveals
        cursor_y = FIRST_BASELINE + LINE * len(self.rows)
        self.row('<tspan class="m">$ </tspan>', f"a {reveals.at(cursor_at)}")
        height = cursor_y + 22
        # Every `reveals.at` call comes before the stylesheet, which lists their rules.
        cursor = (
            f'<g class="a {reveals.at(cursor_at)}"><rect class="blink" x="{PAD_X + 17}" y="{cursor_y - 12}" '
            f'width="8" height="15" fill="{theme.muted}"/></g>'
        )
        style = (
            f"text{{font:14px/1 {FONT};fill:{theme.text};white-space:pre}}"
            f".m,.p{{fill:{theme.muted}}}.k{{fill:{theme.key}}}.x{{fill:{theme.error}}}"
            f".e{{fill:{theme.emphasis};font-weight:600}}.bar{{font-size:12px;fill:{theme.muted}}}"
            + (f".b{{font-weight:600}}.g{{fill:{theme.added}}}" if self.styled else "")
            + f".a{{animation-duration:{LOOP}s;animation-iteration-count:infinite;animation-timing-function:linear}}"
            "@keyframes blink{0%{opacity:1}50%,100%{opacity:0}}"
            ".blink{animation:blink 1.1s steps(1,end) infinite}"
            + "".join(reveals.rules)
            + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
        )
        dots = "".join(
            f'<circle cx="{20 + 18 * i}" cy="{BAR / 2}" r="5" fill="{theme.border}"/>' for i in range(3)
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
            f'role="img" aria-label="{escape(label)}"><title>{escape(label, quote=False)}</title>'
            f"<style>{style}</style>"
            f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{height - 1}" rx="10" fill="{theme.window}" '
            f'stroke="{theme.border}"/>'
            f'<path d="M1 {BAR}V10.5A9.5 9.5 0 0 1 10.5 1H{WIDTH - 10.5}A9.5 9.5 0 0 1 {WIDTH - 1} 10.5V{BAR}Z" '
            f'fill="{theme.bar}"/><path d="M1 {BAR}.5H{WIDTH - 1}" stroke="{theme.border}"/>'
            f"{dots}"
            f'<text class="bar" x="{WIDTH / 2}" y="{BAR / 2 + 4}" text-anchor="middle">{escape(bar, quote=False)}</text>'
            f'<g xml:space="preserve">{"".join(self.rows)}{cursor}</g></svg>\n'
        )

    styled = False  # the upgrade demo's bold and added-line classes


def draw(theme: Theme, finding: dict) -> str:
    term = Terminal()
    reveals = term.reveals
    typed, _ = _typed(SHOW, *TYPE_SHOW, reveals)
    term.row(f'<tspan class="m">$ </tspan>{typed}')
    term.row(f'<tspan class="x">{escape(ERROR, quote=False)}</tspan>', f"a {reveals.at(ERROR_AT, LINE_FADE)}")
    term.row("")
    typed, _ = _typed(EXPLAIN, *TYPE_EXPLAIN, reveals)
    term.row(f'<tspan class="a m {reveals.at(PROMPT_AT)}">$ </tspan>{typed}')
    at = ANSWER_AT
    for spans in answer_lines(finding):
        term.row(_spans(spans), f"a {reveals.at(at, LINE_FADE)}")
        at += ANSWER_STEP
    label = (
        f"Terminal demo. The error: {ERROR} The command: {EXPLAIN} DepTime's answer: "
        f"{finding['symbol']} was removed; the last release with it is {finding['last_version_with']}, the first "
        f"without it {finding['first_version_without']}, and it was deprecated in {finding['deprecated_in']}. "
        f"Use {' or '.join(r['target'] for r in finding['replacements'])} instead, or pin "
        f"{finding['pin_to_restore']}."
    )
    return term.window(theme, at + 0.2, label, "a real answer from the published index, trimmed")


# ------------------------------------------------------------------------------------------- the upgrade check
# A small MCP server that calls an API through a proxy: the two updates Dependabot would open for it.
PROJECT = {
    "requirements.txt": "httpx==0.27.2\nmcp==1.26.0\n",
    "app/server.py": (
        "import httpx\n"
        "from mcp.server.fastmcp import FastMCP\n"
        "\n"
        'mcp = FastMCP("weather")\n'
        'client = httpx.Client(proxies="http://proxy.internal:3128", timeout=10)\n'
        "\n"
        "\n"
        "@mcp.tool()\n"
        "def forecast(city: str) -> str:\n"
        '    return client.get(f"https://api.example.com/forecast/{city}").text\n'
    ),
}
UPDATED = {"requirements.txt": "httpx==0.28.1\nmcp==2.3.0\n"}
DIFF = "git diff -U0 requirements.txt"
CHECK = "deptime check-upgrade"
WRAP = 84  # characters a row holds at 14px in the window
TYPE_DIFF = (0.4, 0.04)
DIFF_AT = 1.9
TYPE_CHECK = (2.9, 0.05)
REPORT_AT, REPORT_STEP = 4.4, 0.12


def _git(cwd: str, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "demo", "GIT_AUTHOR_EMAIL": "demo@example.invalid"}
    env |= {
        "GIT_COMMITTER_NAME": "demo",
        "GIT_COMMITTER_EMAIL": "demo@example.invalid",
        "GIT_CONFIG_GLOBAL": os.devnull,
    }
    return subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True, check=True).stdout


def upgrade_run() -> tuple[list[str], str, int]:
    """The diff's changed lines, the report and the exit code of `deptime check-upgrade` on the demo project."""
    with tempfile.TemporaryDirectory() as root:
        for files in (PROJECT, UPDATED):
            for name, text in files.items():
                path = Path(root, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding="utf-8")
            if files is PROJECT:
                _git(root, "init", "-q")
                _git(root, "add", "-A")
                _git(root, "commit", "-qm", "base")
        diff = [
            line
            for line in _git(root, "diff", "-U0", "requirements.txt").splitlines()
            if line[:1] in "+-" and line[:3] not in {"+++", "---"}
        ]
        run = subprocess.run(["deptime", "check-upgrade", root], capture_output=True, text=True)
    if run.returncode not in (0, 1):
        sys.exit(f"deptime check-upgrade failed ({run.returncode}): {run.stderr.strip()}")
    return diff, run.stdout, run.returncode


_MARK = re.compile(r"(\*\*.+?\*\*|`[^`]+`)")
_REPLACEMENT = ("Try ", "(use ", "(try ")


def _report_spans(line: str) -> list[Span]:
    """One Markdown line as a terminal renderer shows it: bold without asterisks, code without backticks, and the
    replacement a break names emphasised."""
    spans: list[Span] = []
    for part in _MARK.split(line):
        if not part:
            continue
        if part.startswith("**"):
            spans.append(("b", part[2:-2]))
        elif part.startswith("`"):
            before = spans[-1][1] if spans else ""
            spans.append(("e" if before.endswith(_REPLACEMENT) else "k", part[1:-1]))
        else:
            spans.append(("t", part))
    return spans


def _wrap(spans: list[Span], indent: str) -> list[list[Span]]:
    """`spans` in rows of at most WRAP characters, broken at spaces; rows after the first start with `indent`."""
    words: list[Span] = []
    for cls, text in spans:
        words += [(cls, w) for w in re.split(r"(?<= )", text) if w]
    rows: list[list[Span]] = [[]]
    width = 0
    for cls, word in words:
        if width + len(word.rstrip()) > WRAP and width > len(indent):
            rows.append([("t", indent)])
            width = len(indent)
        rows[-1].append((cls, word))
        width += len(word)
    return rows


def report_rows(report: str) -> list[list[Span]]:
    """The report up to its agent block, without the per-package counts and the "Breaks" label, wrapped."""
    rows: list[list[Span]] = []
    for line in report.split("<details>", 1)[0].splitlines():
        if not line.strip() or line.startswith("**Breaks**") or " used in " in line:
            continue
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            if rows and level > 2:
                rows.append([])
            rows.append([("b" if level == 2 else "h", line.lstrip("# "))])
            continue
        indent = " " * (len(line) - len(line.lstrip()) + 2)
        rows += _wrap(_report_spans(line), indent)
    return rows


def draw_upgrade(theme: Theme, diff: list[str], report: str, code: int) -> str:
    term = Terminal()
    term.styled = True
    reveals = term.reveals
    typed, _ = _typed(DIFF, *TYPE_DIFF, reveals)
    term.row(f'<tspan class="m">$ </tspan>{typed}')
    for line in diff:
        term.row(
            _spans([("x" if line.startswith("-") else "g", line)]), f"a {reveals.at(DIFF_AT, LINE_FADE)}"
        )
    term.row("")
    typed, _ = _typed(CHECK, *TYPE_CHECK, reveals)
    term.row(f'<tspan class="a m {reveals.at(TYPE_CHECK[0] - 0.4)}">$ </tspan>{typed}')
    at = REPORT_AT
    rows = report_rows(report)
    for spans in rows:
        term.row(_spans([("b k" if c == "h" else c, s) for c, s in spans]), f"a {reveals.at(at, LINE_FADE)}")
        at += REPORT_STEP
    term.row("")
    term.row('<tspan class="m">$ </tspan><tspan>echo $?</tspan>', f"a {reveals.at(at + 0.4)}")
    term.row(f"<tspan>{code}</tspan>", f"a {reveals.at(at + 0.8, LINE_FADE)}")
    text = " ".join("".join(s for _, s in r).strip() for r in rows if r)
    label = (
        f"Terminal demo. {DIFF} shows the update: {', '.join(diff)}. {CHECK} reports: {text} The exit code is "
        f"{code}, which fails the check."
    )
    return term.window(theme, at + 1.2, label, "a real report from the published index, trimmed")


def main() -> None:
    finding = answer()
    diff, report, code = upgrade_run()
    for theme in (LIGHT, DARK):
        for path, svg in (
            (ASSETS / f"demo-{theme.name}.svg", draw(theme, finding)),
            (ASSETS / f"upgrade-{theme.name}.svg", draw_upgrade(theme, diff, report, code)),
        ):
            path.write_text(svg, encoding="utf-8")
            print(f"wrote {path.relative_to(ASSETS.parents[1])} ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
