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

Run 44088837627, 2026-11-17, `deptime` 0.2.3 from PyPI, two runs per runner. Seconds from launch:

| Runner | Handshake | First call ("no index yet") | Right finding |
|---|---|---|---|
| `ubuntu-24.04` (x86_64) | 2.3, 1.7 | 2.4, 1.8 | **8.4, 7.8** |
| `windows-latest` (AMD64) | 12.0, 11.1 | 12.2, 11.3 | **20.3, 19.2** |
| `macos-latest` (arm64) | 3.3, 3.4 | 3.5, 3.6 | **9.6, 9.7** |
| `macos-15-intel` (x86_64, not held to the bar) | 166.3, 201.9 | 166.6, 202.3 | 175.0, 213.1 |

**Bar met:** every Linux, Windows and Apple-silicon run gave the right finding (`httpx.Client.__init__(proxies)`,
`param_removed`, `httpx<=0.27.2`) in under 21 s. Each first call returned the "no index yet" note, and the index
landed 6 to 9 s after the handshake.

**Windows:** works with no change; the handshake is the slowest of the three (11 to 12 s, uv installing on NTFS).
Replacing the index while the server runs is covered by `test-windows` in `ci` (DT-OSS-08).

**macOS with an x86_64 `uv`:** about 3 minutes before the handshake, all of it compiling `cryptography`, which `mcp`
2.3 requires (`pyjwt[crypto]`) and which has no x86_64 macOS wheel. That is past Claude Code's 30 s connection limit,
so the first start fails there and the second works. DepTime can't drop the dependency; the README's advice (run
`uvx deptime --help` once first) stands, now with this number.
