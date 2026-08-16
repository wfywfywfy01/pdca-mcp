# -*- coding: utf-8 -*-
"""PDCA 经销商数据 MCP 服务配置。

独立于 pdca-workbench 看板，只读查询生产 PostgreSQL。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")


def database_url() -> str:
    """复用生产 PostgreSQL 连接串（只读）。"""
    return os.environ.get(
        "PDCA_MCP_DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/pdca",
    )


def api_key_auth() -> dict[str, dict]:
    """解析 API key → 权限信息。

    格式（逗号分隔多把）：
        key:role:owner_key
    例如：
        admin-xxx:admin:
        sales-yyy:sales:April
        dealer-zzz:dealer:qa-test-01

    role 取值：admin（全部）/ sales（按 owner_key 过滤门店）/ dealer（按门店过滤）。
    不带 role 的 key 默认 admin。
    """
    result: dict[str, dict] = {}
    raw = os.environ.get("PDCA_MCP_API_KEYS", "")
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        parts = [p.strip() for p in item.split(":")]
        key = parts[0]
        role = parts[1] if len(parts) > 1 and parts[1] else "admin"
        owner_key = parts[2] if len(parts) > 2 else ""
        result[key] = {"role": role, "owner_key": owner_key}
    return result


def vertu_command() -> str:
    return os.environ.get("VERTU_COMMAND", "vertu-cli")
