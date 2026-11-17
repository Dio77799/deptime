"""S7 (DT-SPIKE-07): time a first launch, from nothing to a useful answer.

    uv run python bench/s7/first_run.py 0.2.3

Starts `uvx deptime==<version> mcp` the way an MCP client does, with an empty uv cache (so uvx installs DepTime and
its dependencies from PyPI) and an empty DepTime home (so there is no index yet). Then calls explain_error on httpx
0.28's removed `proxies` every 2 seconds until an answer has a finding, for up to 5 minutes. Prints one JSON line:
seconds to the handshake, the first call's note, seconds to the first finding, and the finding.
"""

import asyncio
import json
import os
import platform
import shutil
import sys
import tempfile
import time

from mcp import Client, StdioServerParameters

TB = (
    "Traceback (most recent call last):\n"
    '  File "/app/main.py", line 3, in <module>\n'
    '    client = httpx.Client(proxies="http://localhost:8030")\n'
    "TypeError: Client.__init__() got an unexpected keyword argument 'proxies'\n"
)
DEADLINE = 300.0


async def main(version: str) -> int:
    work = tempfile.mkdtemp(prefix="deptime-s7-")
    env = {
        **os.environ,
        "UV_CACHE_DIR": os.path.join(work, "uv-cache"),
        "DEPTIME_HOME": os.path.join(work, "home"),
    }
    for key in ("DEPTIME_OFFLINE", "DEPTIME_INDEX_PATH", "DEPTIME_INDEX_URL", "UV_OFFLINE"):
        env.pop(key, None)
    uvx = shutil.which("uvx") or "uvx"
    params = StdioServerParameters(command=uvx, args=[f"deptime=={version}", "mcp"], env=env)
    out: dict = {"os": platform.system(), "machine": platform.machine(), "version": version}
    start = time.monotonic()
    async with Client(params) as client:
        out["handshake_s"] = round(time.monotonic() - start, 1)
        calls = 0
        while time.monotonic() - start < DEADLINE:
            result = await client.call_tool(
                "explain_error", {"traceback": TB, "installed_versions": {"httpx": "0.28.1"}}
            )
            calls += 1
            body = result.structured_content or {}
            if calls == 1:
                out["first_call_s"] = round(time.monotonic() - start, 1)
                out["first_call_note"] = body.get("note")
            findings = body.get("findings") or []
            if findings:
                top = findings[0]
                out["answer_s"] = round(time.monotonic() - start, 1)
                out["finding"] = [top.get("symbol"), top.get("issue"), top.get("pin_to_restore")]
                break
            await asyncio.sleep(2)
        out["calls"] = calls
    print(json.dumps(out))
    return 0 if "answer_s" in out else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(sys.argv[1])))
