# S5: client compatibility (DT-SPIKE-05)

**Question:** does `uvx deptime mcp` work in the MCP clients people use, and does the hosted server (`deptime serve`, spec 2026-07-28, stateless) still answer clients that open with the older `initialize` handshake?

## Scripts

- `py_client.py`: an MCP Python SDK 1.x client, over stdio (launching the server as a client would) or Streamable HTTP.
- `ts_client.mjs`: the same with the MCP TypeScript SDK.

Each one does the handshake, lists the tools and calls `explain_error` on httpx 0.28's removed `proxies`, then prints one JSON line. An old SDK resolves its dependencies as of a week after its release (`--exclude-newer`), as a client built then would have. The 2.x Python SDK is covered by the test suite (`tests/test_stdio.py`, the hosted tests).

## Results (2026-11-05, `deptime` 0.1.4 from PyPI)

**SDK clients, every protocol version from 2024-11-05 to 2025-11-25: all pass.** Each completed the handshake, listed the five tools, and got `httpx.Client.__init__(proxies)`, `param_removed`.

| Client | stdio (`uvx deptime@0.1.4 mcp`) | Streamable HTTP (`deptime serve`) | Protocol negotiated |
|---|---|---|---|
| Python SDK 1.0.0, 1.2.0, 1.6.0 | ✅ | ✅ 1.8.0 (first with Streamable HTTP) | 2024-11-05 |
| Python SDK 1.9.4 | ✅ | ✅ | 2025-03-26 |
| Python SDK 1.12.4, 1.22.0 | ✅ | ✅ | 2025-06-18 |
| Python SDK 1.30.0 | ✅ | ✅ | 2025-11-25 |
| TypeScript SDK 1.0.0, 1.8.0, 1.13.0, 1.23.0, 1.32.0 | ✅ | ✅ 1.10.0 (first with Streamable HTTP), 1.13.0, 1.23.0, 1.32.0 | the SDK's latest |

**Clients:**

| Client | How | Result |
|---|---|---|
| Claude Code 2.1.318 | `claude -p … --mcp-config <file> --strict-mcp-config`, DepTime the only server | ✅ The right finding and pin. With an empty `DEPTIME_HOME`, the first call returns "DepTime has no index yet. The first run downloads it in the background; retry in a minute…", and the index lands about 10 s after start. |
| Codex CLI 0.166.0 | `codex exec -s read-only -c mcp_servers.deptime.command="uvx" -c mcp_servers.deptime.args=[…]` | ✅ The right finding and pin. |
| Claude Desktop 1.15962.1 (macOS, 2026-11-17, `deptime` 1.0.1) | `"mcpServers": {"deptime": {"command": "uvx", "args": ["deptime", "mcp"]}}` in `claude_desktop_config.json`, as the README says; a bare `uvx`, no full path | ✅ It called DepTime and gave the right finding, replacement and pin. Its log shows the server up a second after launch and the handshake answered 9 to 16 s later (an x86_64 `uv` under Rosetta, cache already warm). |
| VS Code 1.131.0 with Copilot Free (macOS, 2026-11-17, `deptime` 1.0.1) | `{"servers": {"deptime": {"type": "stdio", "command": "uvx", "args": ["deptime", "mcp"]}}}` in the user `mcp.json`; Agent mode | ✅ It found the six tools 4 s after start, called `explain_error` and gave the right finding, replacement and pin. |
| Cursor | | Not run yet. |

**Findings:**

- **A slow first install can outlast a client's startup limit.** `uvx` installs DepTime the first time a client starts it. On macOS with an x86_64 `uv` (an Intel Mac, or an Intel Homebrew `uv` on Apple silicon, as on the test machine), `cryptography`, which the MCP SDK requires through `pyjwt[crypto]`, has had no wheel since 49.0, so it is compiled from source: 62 s on the test machine, past Claude Code's 30 s MCP connection timeout. The second launch is fast. The README says to run `uvx deptime --help` once first.
- **An interrupted first download recovers.** A one-shot session that exits during the download leaves `index.sqlite.download*` behind; the next start replaces them and installs the index.
- **stderr is chatty.** The MCP SDK sets up INFO logging, so httpx logs each download request with its full signed URL (short-lived, for a public asset). Harmless, and it stays off stdout (`tests/test_stdio.py`), but it is noise in a client's MCP log.

**Re-check, 2026-11-17, `deptime` 1.0.0 from PyPI:** Claude Code 2.1.326 (`claude -p` with `--mcp-config` and
`--strict-mcp-config`, DepTime the only server) called `explain_error` and answered "removed in httpx 0.28.0",
pin `httpx<=0.27.2`. ✅
