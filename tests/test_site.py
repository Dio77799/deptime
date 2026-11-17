"""Rename-map pages generated from the index (DT-GTM-01)."""

from deptime.models import Replacement
from deptime.site import Migration, Range, _evidence, build


def test_a_rename_map_lists_what_replaces_each_name(dt, tmp_path):
    migration = Migration("httpx-0.26-to-0.28", "httpx 0.26 → 0.28", (Range("httpx", "0.26."),))
    written = build(dt, tmp_path, (migration,), base_url="https://example.invalid/")
    assert {p.name for p in written} == {"httpx-0.26-to-0.28.html", "index.html", "llms.txt", "sitemap.xml"}
    page = (tmp_path / "httpx-0.26-to-0.28.html").read_text(encoding="utf-8")
    assert "httpx 0.26.0 → 0.28.1" in page
    assert "<code>httpx.OldThing</code></td><td><code>httpx.NewThing</code>" in page
    assert (
        "<code>httpx.Client.__init__(proxies)</code></td><td><code>proxy</code> or <code>mounts</code>"
        in page
    )
    assert "- [httpx 0.26 → 0.28](httpx-0.26-to-0.28.html): 2 names replaced, 0 removed" in (
        tmp_path / "llms.txt"
    ).read_text(encoding="utf-8")
    assert "https://example.invalid/httpx-0.26-to-0.28.html" in (tmp_path / "sitemap.xml").read_text(
        encoding="utf-8"
    )


def test_library_text_is_escaped_on_the_page():
    r = Replacement(target="x", confidence=0.9, source="deprecation_message", evidence="use <b>x</b> & not y")
    assert "&lt;b&gt;x&lt;/b&gt; &amp; not y" in _evidence(r)


def test_each_page_has_a_search_title_description_and_canonical_url(dt, tmp_path):
    migration = Migration("httpx-0.26-to-0.28", "httpx 0.26 → 0.28", (Range("httpx", "0.26."),))
    build(dt, tmp_path, (migration,), base_url="https://example.invalid/")
    page = (tmp_path / "httpx-0.26-to-0.28.html").read_text(encoding="utf-8")
    assert "<title>httpx 0.26 → 0.28 migration: renamed and removed names</title>" in page
    assert '<meta name="description" content="httpx 0.26 → 0.28: 2 names and arguments' in page
    assert '<link rel="canonical" href="https://example.invalid/httpx-0.26-to-0.28.html">' in page
    assert "uvx deptime check-upgrade" in page  # the way back to DepTime from a search
    landing = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://example.invalid/">' in landing
    assert '<a href="httpx-0.26-to-0.28.html">httpx 0.26 → 0.28</a> (2 replaced, 0 removed)' in landing
    assert f"of {len(dt.coverage.packages)} fast-moving Python libraries" in landing


def test_without_a_base_url_there_is_no_canonical_url_or_sitemap(dt, tmp_path):
    migration = Migration("httpx-0.26-to-0.28", "httpx 0.26 → 0.28", (Range("httpx", "0.26."),))
    written = build(dt, tmp_path, (migration,))
    assert "sitemap.xml" not in {p.name for p in written}
    assert 'rel="canonical"' not in (tmp_path / "httpx-0.26-to-0.28.html").read_text(encoding="utf-8")


def test_paths_no_one_writes_are_left_off_the_maps():
    from deptime.site import _artefact

    assert _artefact("pydantic.v1.v1.BaseModel")  # a module seen through itself
    assert _artefact("pydantic.config.DeprecationWarning")  # a builtin the module imports
    assert not _artefact("pydantic.v1.BaseModel")
    assert not _artefact("httpx.Client.__init__")
    assert not _artefact("langchain_core.tools.BaseTool.list")
    assert not _artefact("requests.ConnectionError")
