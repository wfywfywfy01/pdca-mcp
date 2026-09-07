import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ["PDCA_MCP_DATABASE_URL"] = os.environ["PDCA_MCP_TEST_DATABASE_URL"]
os.environ["PDCA_MCP_API_KEYS"] = "test-key-123"
os.environ["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

PORT = 8899
URL = f"http://127.0.0.1:{PORT}/mcp"


async def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "pdca_mcp.server", "--transport", "http", "--port", str(PORT)],
        env=os.environ.copy(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    time.sleep(5)
    result = None
    try:
        async with streamablehttp_client(URL, headers={"Authorization": "Bearer test-key-123"}) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                r = await session.call_tool("query_stores", {"region": "中东"})
                result = r.content[0].text
    except BaseException as e:
        result = f"EXC: {type(e).__name__}: {e}"
    finally:
        proc.terminate()

    if result and not str(result).startswith("EXC"):
        payload = json.loads(result)
        print("HTTP_OK 中东门店数:", payload.get("count"))
    else:
        print("HTTP 结果:", str(result)[:300])


if __name__ == "__main__":
    asyncio.run(main())
