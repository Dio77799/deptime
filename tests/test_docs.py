import json
import re
from pathlib import Path

from deptime import __version__
from deptime.config import load_coverage

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def test_readme_package_count_matches_coverage():
    """The README states the coverage count once; it has to change in the same commit as coverage.toml."""
    counts = re.findall(r"\b(\d+) fast-moving packages\b", README.read_text(encoding="utf-8"))
    assert counts == [str(len(load_coverage().packages))], "update the count in README.md's Tools table"


def test_the_plugin_runs_this_release_and_names_its_icon():
    """Anthropic's plugin directory rejects a launcher that isn't pinned to an exact version and takes the listing's
    icon from the manifest, so the plugin runs the release its manifest names: a release moves both."""
    plugin = ROOT / "integrations" / "claude-code"
    manifest = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    server = json.loads((plugin / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["deptime"]
    assert manifest["version"] == __version__
    assert (server["command"], server["args"]) == ("uvx", [f"deptime=={__version__}", "mcp"])
    assert (plugin / manifest["icon"]).is_file()


def test_registry_server_json_matches_the_release():
    """The MCP Registry rejects a publish unless server.json names this release and the README carries its mcp-name."""
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    assert server["version"] == __version__
    assert [p["version"] for p in server["packages"]] == [__version__]
    assert re.findall(r"mcp-name: (\S+) ", README.read_text(encoding="utf-8")) == [server["name"]]
