# -*- coding: utf-8 -*-
"""PDCA 经销商数据 MCP Server（只读查询）。

独立于 pdca-workbench 看板，直接只读查询生产 PostgreSQL。
启动：
    # 本地 stdio（默认，配置到 Claude Desktop / Cursor / opencode）
    python -m pdca_mcp.server

    # 远程 HTTP（团队共享，配 URL + API key）
    python -m pdca_mcp.server --transport http --port 8765
"""
from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from . import db

mcp = FastMCP("pdca-mcp")


@mcp.tool()
def query_stores(region: str = "") -> list[dict]:
    """查询活跃门店列表。

    Args:
        region: 大区过滤（中东/欧洲/南亚/东南亚/中亚），留空返回全部。
    """
    return db.list_stores(region)


@mcp.tool()
def query_sell_in(month: str) -> dict:
    """查询经销商进货（Sell-in）金额。

    口径：VERTU 卖给经销商的订单金额，单位「万 CNY」。

    Args:
        month: 月份，格式 YYYY-MM（如 2026-08）。
    """
    return db.sell_in_summary(month)


@mcp.tool()
def query_sell_out(month: str) -> dict:
    """查询经销商终销（Sell-out）金额。

    口径：门店五件套上报的成交金额，单位「USD」。

    Args:
        month: 月份，格式 YYYY-MM。
    """
    return db.sell_out_summary(month)


@mcp.tool()
def query_five_kit(month: str, dealer_id: str = "") -> list[dict]:
    """查询门店五件套日报明细（客流来源 + 成交漏斗）。

    Args:
        month: 月份，格式 YYYY-MM。
        dealer_id: 门店 ID（如 sea02a），留空返回全部门店。
    """
    return db.five_kit(month, dealer_id)


@mcp.tool()
def query_meetings(date: str) -> list[dict]:
    """查询某天的会议记录（含待办）。

    Args:
        date: 日期，格式 YYYY-MM-DD。
    """
    return db.meetings(date)


@mcp.tool()
def query_monthly_targets(month: str) -> list[dict]:
    """查询月度目标（全局 + 按门店）。

    Args:
        month: 月份，格式 YYYY-MM。
    """
    return db.monthly_targets(month)


def main() -> None:
    parser = argparse.ArgumentParser(description="PDCA 经销商数据 MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.transport == "http":
        mcp.run(transport="http", host="0.0.0.0", port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
