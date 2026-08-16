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

from mcp.server.fastmcp import Context, FastMCP

from . import config, db

mcp = FastMCP("pdca-mcp")


def _owner_scope(ctx: Context | None) -> str:
    """从 MCP Context 解析当前 key 的 owner_key（数据范围）。

    admin/viewer 返回空串（不过滤）；sales/dealer 返回其绑定的 owner_key。
    stdio 模式无 HTTP 请求头，默认 admin（不过滤）。
    """
    if ctx is None:
        return ""
    try:
        request = ctx.request_context.request
        auth = (request.headers.get("authorization") or "") if request else ""
    except Exception:
        return ""
    key = auth.replace("Bearer ", "").strip()
    info = config.api_key_auth().get(key, {})
    role = info.get("role", "admin")
    if role in ("sales", "dealer"):
        return info.get("owner_key", "")
    return ""


@mcp.tool()
def query_stores(region: str = "", ctx: Context | None = None) -> dict:
    """查询活跃门店列表。

    Args:
        region: 大区过滤（中东/欧洲/南亚/东南亚/中亚），留空返回全部。
    """
    stores = db.list_stores(region, _owner_scope(ctx))
    return {"count": len(stores), "stores": stores}


@mcp.tool()
def query_sell_in(month: str, ctx: Context | None = None) -> dict:
    """查询经销商进货（Sell-in）金额。

    口径：VERTU 卖给经销商的订单金额，单位「万 CNY」。

    Args:
        month: 月份，格式 YYYY-MM（如 2026-08）。
    """
    return db.sell_in_summary(month, _owner_scope(ctx))


@mcp.tool()
def query_sell_out(month: str, ctx: Context | None = None) -> dict:
    """查询经销商终销（Sell-out）金额。

    口径：门店五件套上报的成交金额，单位「USD」。

    Args:
        month: 月份，格式 YYYY-MM。
    """
    return db.sell_out_summary(month, _owner_scope(ctx))


@mcp.tool()
def query_five_kit(month: str, dealer_id: str = "", ctx: Context | None = None) -> dict:
    """查询门店五件套日报明细（客流来源 + 成交漏斗）。

    Args:
        month: 月份，格式 YYYY-MM。
        dealer_id: 门店 ID（如 sea02a），留空返回权限范围内的门店。
    """
    items = db.five_kit(month, dealer_id, _owner_scope(ctx))
    return {"count": len(items), "items": items}


@mcp.tool()
def query_meetings(date: str) -> dict:
    """查询某天的会议记录（含待办）。

    Args:
        date: 日期，格式 YYYY-MM-DD。
    """
    items = db.meetings(date)
    return {"count": len(items), "items": items}


@mcp.tool()
def query_monthly_targets(month: str) -> dict:
    """查询月度目标（全局 + 按门店）。

    Args:
        month: 月份，格式 YYYY-MM。
    """
    items = db.monthly_targets(month)
    return {"count": len(items), "items": items}


@mcp.tool()
def query_logistics_track(carrier: str, tracking_number: str) -> dict:
    """生成物流单号查询链接（UPS / FedEx / DHL）。

    返回承运商官网查询链接，供人工点击核对状态。

    Args:
        carrier: 承运商（UPS / FedEx / DHL）。
        tracking_number: 运单号。
    """
    templates = {
        "UPS": "https://www.ups.com/track?loc=en_US&tracknum={tn}",
        "FedEx": "https://www.fedex.com/fedextrack/?trknbr={tn}",
        "DHL": "https://www.dhl.com/global-en/home/tracking.html?tracking-id={tn}",
    }
    key = (carrier or "").strip().upper()
    template = templates.get(key)
    if not template:
        return {
            "carrier": key,
            "tracking_number": tracking_number,
            "error": f"不支持的承运商「{carrier}」，支持 UPS / FedEx / DHL",
        }
    return {
        "carrier": key,
        "tracking_number": tracking_number,
        "tracking_url": template.format(tn=tracking_number),
    }


# ── HTTP API key 认证（streamable-http 模式）─────────────────────────────────

def _auth_middleware(app):
    """纯 ASGI 中间件：HTTP 模式下校验 Authorization: Bearer <key>。

    只在建立 session 的初始请求校验 key；带 Mcp-Session-Id 的后续请求
    复用已认证会话，不再要求 Authorization header（MCP streamable-http 协议如此）。
    """
    auth_map = config.api_key_auth()

    async def wrapper(scope, receive, send):
        if scope["type"] == "lifespan":
            # 必须转发 lifespan，否则 Starlette 不会启动 session_manager.run()，
            # streamable-http 的 task_group 未初始化会直接 404。
            await app(scope, receive, send)
            return
        if scope["type"] != "http":
            await app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        # 已建立会话的后续请求直接放行
        if b"mcp-session-id" in headers:
            await app(scope, receive, send)
            return
        auth = headers.get(b"authorization", b"").decode("utf-8", "replace")
        key = auth.replace("Bearer ", "").strip()
        if auth_map and key not in auth_map:
            from starlette.responses import JSONResponse

            response = JSONResponse({"detail": "invalid or missing api key"}, status_code=401)
            await response(scope, receive, send)
            return
        await app(scope, receive, send)

    return wrapper


def build_http_app():
    """返回带 API key 认证的 ASGI app。"""
    return _auth_middleware(mcp.streamable_http_app())


def main() -> None:
    parser = argparse.ArgumentParser(description="PDCA 经销商数据 MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    if args.transport == "http":
        import uvicorn

        # build_http_app() 已包含 API key 认证 + lifespan 转发
        uvicorn.run(build_http_app(), host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
