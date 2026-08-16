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


def api_keys() -> set[str]:
    """MCP 访问密钥集合（逗号分隔，支持多把 key 分发给不同使用者）。"""
    raw = os.environ.get("PDCA_MCP_API_KEYS", "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def vertu_command() -> str:
    return os.environ.get("VERTU_COMMAND", "vertu-cli")
