import asyncio
import os
import sys

os.environ["PYTHONPATH"] = r"D:\pdca-mcp\src" + os.pathsep + os.environ.get("PYTHONPATH", "")

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://10.100.0.176:8899/mcp"


async def call(key, tool, args):
    headers = {"Authorization": f"Bearer {key}"}
    try:
        async with streamablehttp_client(URL, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                r = await session.call_tool(tool, args)
                return eval(r.content[0].text)
    except BaseException as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def main():
    admin = await call("pdca-admin-2026", "query_stores", {"region": ""})
    april = await call("pdca-april-2026", "query_stores", {"region": ""})
    bad = await call("wrong-key", "query_stores", {"region": ""})
    sell_in = await call("pdca-admin-2026", "query_sell_in", {"month": "2026-08"})

    print("admin key 门店数:", admin.get("count") if isinstance(admin, dict) else admin)
    print("April key 门店数:", april.get("count") if isinstance(april, dict) else april)
    print("错误 key:", bad)
    print("admin sell_in 总额(万):", sell_in.get("total_wan") if isinstance(sell_in, dict) else sell_in)


if __name__ == "__main__":
    asyncio.run(main())
