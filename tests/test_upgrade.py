"""`deptime check-upgrade` on the synthetic 3-release httpx index (DT-CORE-58, DT-CORE-59)."""

from __future__ import annotations

import json
import subprocess

from deptime import cli, snippet
from deptime.index.store import IndexStore
from deptime.ingest.snapshot import ApiSnapshot, SymbolRecord
from deptime.models import DependencyChange
from deptime.query import DepTime
from deptime.suppressions import Suppression
from deptime.upgrade import check_upgrade, own_modules, project_files, to_markdown
from tests.conftest import HTTPX

CODE = """import httpx

client = httpx.Client(proxies="http://p", timeout=5)
client.get("https://example.invalid")
thing = httpx.OldThing()
"""


def _change(frm: str | None, to: str | None, package: str = "httpx") -> DependencyChange:
    return DependencyChange(package=package, from_version=frm, to_version=to, source="uv.lock")


def test_reader_records_lines_of_uses_calls_and_keywords():
    uses = snippet.uses_in(CODE, ("httpx",))
    assert uses is not None
    assert uses.lines["httpx"] == [1]
    assert uses.lines["httpx.Client"] == [3] and uses.call_lines["httpx.Client"] == [3]
    assert uses.kwarg_lines[("httpx.Client", "proxies")] == [3]
    assert uses.lines[("httpx.Client", "get")] == [4]


def test_a_removed_keyword_is_a_break_with_where_and_what_replaces_it(dt):
    res = check_upgrade(dt, "proj", {"app/main.py": CODE}, [_change("0.27.2", "0.28.1")])
    (pkg,) = res.checked
    assert res.breaks == 1 and pkg.resolved_version == "0.28.1" and pkg.files == 1
    (b,) = pkg.breaks
    assert (b.path, b.kind, b.kwarg) == ("httpx.Client", "rejected_kwarg", "proxies")
    assert [(loc.file, loc.line) for loc in b.locations] == [("app/main.py", 3)]
    assert b.finding is not None and b.finding.issue == "param_removed"
    assert b.finding.last_version_with == "0.27.2" and b.finding.first_version_without == "0.28.1"
    assert b.finding.replacements[0].target == "proxy"
    # OldThing was already gone at 0.27.2: flagged at both ends, so not this update's doing
    (before,) = [n for n in pkg.notices if n.status == "failing_before"]
    assert before.path == "httpx.OldThing" and before.locations[0].line == 5
    md = to_markdown(res)
    assert "**1 break found**" in md and "`httpx.Client(proxies=)`" in md and "`app/main.py:3`" in md


def test_a_removed_name_with_its_replacement(dt):
    res = check_upgrade(dt, "proj", {"a.py": CODE}, [_change("0.26.0", "0.27.2")])
    (pkg,) = res.checked
    (b,) = pkg.breaks
    assert (b.path, b.kind) == ("httpx.OldThing", "missing")
    assert b.finding is not None and b.finding.issue == "symbol_removed"
    assert b.finding.replacements[0].target == "httpx.NewThing"


def test_deprecations_are_warnings_new_or_already_there(coverage):
    def snap(version: str, deprecated: bool) -> ApiSnapshot:
        symbols = [
            SymbolRecord("httpx", "module", "httpx"),
            SymbolRecord(
                "httpx.Old", "class", "httpx._o.Old", None, "Old is deprecated." if deprecated else None
            ),
        ]
        return ApiSnapshot(
            package="httpx", version=version, import_names=["httpx"], symbols={s.path: s for s in symbols}
        )

    store = IndexStore.memory()
    store.rebuild_package(
        HTTPX,
        [snap("1.0", False), snap("1.1", True), snap("1.2", True)],
        dict.fromkeys(["1.0", "1.1", "1.2"]),
    )
    dt = DepTime(store, coverage)
    code = {"a.py": "from httpx import Old\n"}
    (new,) = check_upgrade(dt, "p", code, [_change("1.0", "1.1")]).checked[0].notices
    assert (new.status, new.new, new.deprecated_in, new.detail) == (
        "deprecated",
        True,
        "1.1",
        "Old is deprecated.",
    )
    res = check_upgrade(dt, "p", code, [_change("1.1", "1.2")])
    assert res.breaks == 0 and res.checked[0].notices[0].new is False
    assert "**Deprecated at the new version**" in to_markdown(
        check_upgrade(dt, "p", code, [_change("1.0", "1.2")])
    )
    assert "Already deprecated at the old version: 1" in to_markdown(res)


def test_a_downgrade_flags_what_isnt_added_yet(dt):
    res = check_upgrade(dt, "proj", {"a.py": "from httpx import NewThing\n"}, [_change("0.27.2", "0.26.0")])
    (b,) = res.checked[0].breaks
    assert b.path == "httpx.NewThing" and b.finding is not None and b.finding.issue == "symbol_not_yet_added"


def test_no_break_exits_clean_and_unknown_never_fails(dt):
    res = check_upgrade(
        dt, "proj", {"a.py": "import httpx\nhttpx.request('GET', 'u')\n"}, [_change("0.27.2", "0.28.1")]
    )
    assert res.breaks == 0 and res.checked[0].breaks == []
    assert "**No breaks found**" in to_markdown(res)


def test_changes_that_are_not_upgrades_or_not_covered(dt):
    res = check_upgrade(
        dt,
        "proj",
        {"a.py": CODE},
        [
            _change(None, "0.28.1"),
            _change("1.0", "2.0", "left-pad"),
            _change("0.27.2", "0.28.1", "google-genai"),
        ],
    )
    assert [c.package for c in res.skipped] == ["httpx"]
    assert [c.package for c in res.not_covered] == [
        "left-pad",
        "google-genai",
    ]  # google-genai: covered, not indexed
    assert res.checked == [] and "nothing was checked" in to_markdown(res)


def test_a_project_module_named_like_the_package_is_its_own_code(dt):
    assert own_modules(["httpx.py", "src/pkg/__init__.py", "tests/test_a.py", "lib/x/__init__.py"]) == {
        "httpx",
        "pkg",
    }
    res = check_upgrade(dt, "proj", {"httpx.py": "", "a.py": CODE}, [_change("0.27.2", "0.28.1")])
    assert res.breaks == 0 and "its own `httpx` module" in (res.checked[0].note or "")


def test_suppressions_and_unparsable_files_are_counted(dt):
    dt.suppressions = (Suppression("httpx", "httpx.Client", "param_removed"),)
    res = check_upgrade(dt, "proj", {"a.py": CODE, "py2.py": "print 'hi'\n"}, [_change("0.27.2", "0.28.1")])
    assert res.breaks == 0 and res.suppressed == 1
    assert res.files_unreadable == ["py2.py"] and res.files_read == 1
    assert "didn't parse" in (res.note or "") and "suppressions" in (res.note or "")


def test_library_text_cannot_render_as_markup(dt):
    from deptime.models import PackageUpgrade, UpgradeCheckResult, UpgradeNotice

    res = UpgradeCheckResult(
        project="p",
        checked=[
            PackageUpgrade(
                change=_change("1", "2"),
                resolved_version="2",
                exact=True,
                uses=1,
                files=1,
                notices=[
                    UpgradeNotice(path="httpx.x", status="deprecated", detail="see [here](https://evil) <b>")
                ],
            )
        ],
    )
    md = to_markdown(res)
    assert "\\[here\\](https://evil) \\<b\\>" in md


def test_project_files_follow_gitignore(tmp_path):
    subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
    for rel in ("a.py", "pkg/b.py", "build/c.py", ".venv/lib/d.py", "ignored/e.py", "notes.txt"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("")
    (tmp_path / ".gitignore").write_text("ignored/\n")
    assert project_files(tmp_path) == ["a.py", "pkg/b.py"]
    (tmp_path / ".git").rename(tmp_path / "not-git")  # no git: a walk that skips the same directories
    assert project_files(tmp_path) == ["a.py", "ignored/e.py", "pkg/b.py"]


def _cli(monkeypatch, settings, *args: str) -> int:
    monkeypatch.setattr(cli.Settings, "from_env", classmethod(lambda cls: settings))
    return cli.main(["check-upgrade", *args])


def test_cli_exits_1_on_a_break_and_writes_json(tmp_path, settings, monkeypatch, capsys):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "main.py").write_text(CODE)
    (proj / "requirements.txt").write_text("httpx==0.27.2\n")
    out = tmp_path / "report.json"
    assert (
        _cli(
            monkeypatch,
            settings,
            str(proj),
            "--package",
            "httpx",
            "--to",
            "0.28.1",
            "--format",
            "json",
            "--output",
            str(out),
        )
        == 1
    )
    data = json.loads(out.read_text())
    assert data["breaks"] == 1 and data["checked"][0]["change"]["from_version"] == "0.27.2"
    assert data["checked"][0]["change"]["source"] == "requirements.txt"
    assert (
        _cli(monkeypatch, settings, str(proj), "--package", "httpx", "--from", "0.28.1", "--to", "0.28.1")
        == 0
    )
    assert "No breaks found" in capsys.readouterr().out


def test_cli_reads_the_change_from_git(tmp_path, settings, monkeypatch, capsys):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "main.py").write_text(CODE)
    (proj / "pyproject.toml").write_text('[project]\nname = "proj"\ndependencies = ["httpx==0.27.2"]\n')
    git = ["git", "-C", str(proj), "-c", "user.email=t@example.invalid", "-c", "user.name=t"]
    subprocess.run([*git, "init", "-q"], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "base"], check=True)
    assert _cli(monkeypatch, settings, str(proj)) == 0  # nothing changed against HEAD
    assert "nothing was checked" in capsys.readouterr().out
    (proj / "pyproject.toml").write_text('[project]\nname = "proj"\ndependencies = ["httpx==0.28.1"]\n')
    assert _cli(monkeypatch, settings, str(proj), "--base", "HEAD") == 1
    assert "httpx 0.27.2 → 0.28.1" in capsys.readouterr().out


def test_cli_usage_errors(tmp_path, settings, monkeypatch, capsys):
    assert _cli(monkeypatch, settings, str(tmp_path / "missing")) == 2
    assert _cli(monkeypatch, settings, str(tmp_path), "--package", "httpx") == 2
    assert _cli(monkeypatch, settings, str(tmp_path), "--package", "httpx", "--to", "0.28.1") == 2
    assert "pass --from" in capsys.readouterr().err


def test_a_spread_call_in_any_file_covers_every_parameter(dt):
    """`httpx.request(*args)` in one file: the other file's call with no arguments doesn't count as missing them."""
    code = {"a.py": "import httpx\nhttpx.request(*args)\n", "b.py": "import httpx\nhttpx.request()\n"}
    for files in (code, dict(reversed(code.items()))):
        res = check_upgrade(dt, "p", files, [_change("0.27.2", "0.28.1")])
        assert res.breaks == 0, files


def test_warnings_about_project_code_stay_quiet(dt, recwarn):
    check_upgrade(dt, "p", {"a.py": 'import httpx\nx = "\\ "\n'}, [_change("0.27.2", "0.28.1")])
    assert not [w for w in recwarn if issubclass(w.category, SyntaxWarning)]
