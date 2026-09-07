import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ["PDCA_MCP_DATABASE_URL"] = os.environ["PDCA_MCP_TEST_DATABASE_URL"]
os.environ["PDCA_MCP_API_KEYS"] = "admin-key:admin:,april-key:sales:April"
os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORT = 8899
URL = f"http://127.0.0.1:{PORT}/mcp"


async def call(key, tool, args):
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with streamablehttp_client(URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                r = await session.call_tool(tool, args)
                return json.loads(r.content[0].text)
    except BaseException as e:
        return f"EXC {type(e).__name__}"


async def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "pdca_mcp.server", "--transport", "http", "--port", str(PORT)],
        env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(5)

    admin_stores = await call("admin-key", "query_stores", {"region": ""})
    april_stores = await call("april-key", "query_stores", {"region": ""})
    april_sell_out = await call("april-key", "query_sell_out", {"month": "2026-08"})

    print("admin key 门店数:", admin_stores.get("count") if isinstance(admin_stores, dict) else "ERROR")
    print("sales key 门店数:", april_stores.get("count") if isinstance(april_stores, dict) else "ERROR")
    print("sales Sell-out 请求成功:", isinstance(april_sell_out, dict))

    proc.terminate()


if __name__ == "__main__":
    asyncio.run(main())
