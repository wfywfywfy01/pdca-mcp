import asyncio
import os
import subprocess
import sys
import time

os.environ["PDCA_MCP_DATABASE_URL"] = "postgresql://postgres:H1UaJoeo-aSF-zpM6V-0ARP@10.100.0.176:5432/pdca"
os.environ["PDCA_MCP_API_KEYS"] = "test-key-123"
os.environ["PYTHONPATH"] = r"D:\pdca-mcp\src" + os.pathsep + os.environ.get("PYTHONPATH", "")

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
        stores = eval(result)
        print("HTTP_OK 中东门店数:", len(stores))
        print("样例:", stores[0]["name"] if stores else "无")
    else:
        print("HTTP 结果:", str(result)[:300])


if __name__ == "__main__":
    asyncio.run(main())
