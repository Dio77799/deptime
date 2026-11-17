# S7: first launch on Linux, Windows and macOS (DT-SPIKE-07)

**Question:** from nothing (no uv cache, no index), how long until a client that starts `uvx deptime mcp` gets a
useful answer, on each operating system?

**Bar (fixed 2026-11-17, before the scored run):** the right finding (`httpx.Client.__init__(proxies)`,
`param_removed`, `httpx<=0.27.2`) within 60 s of launch on Linux, Windows and macOS on Apple silicon, in every run.
macOS with an x86_64 `uv` is reported but not held to the bar: it compiles `cryptography` from source (no wheel since
49.0), which DepTime doesn't control and the README already warns about (DT-SPIKE-05).

**How:** `first_run.py` starts `uvx deptime==<version> mcp` with an empty `UV_CACHE_DIR` and an empty
`DEPTIME_HOME`, through the MCP Python SDK client DepTime's tests use, then calls `explain_error` every 2 s until an
answer has a finding (5 minutes at most). The `s7` workflow (`workflow_dispatch`) runs it twice on each of
`ubuntu-24.04`, `windows-latest`, `macos-latest` (arm64) and `macos-15-intel`, against the release on PyPI.

**Caveat:** GitHub's runners have fast networks; a home connection downloads the 51 MB index more slowly. The index
download happens in the background after the handshake, so a slow download delays the answer, not the start.

**Trial (not scored), 2026-11-17, this repo's Mac with an x86_64 `uv`:** handshake 131.7 s (the `cryptography`
compile), first call 132.0 s with the "no index yet" note, answer at 138.0 s. The script works end to end.

## Results
