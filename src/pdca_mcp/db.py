# -*- coding: utf-8 -*-
"""只读查询生产 PostgreSQL。所有查询均不加任何写锁，只 SELECT。"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import math

import psycopg2
from psycopg2.extras import RealDictCursor

from .config import database_url


@contextmanager
def _cursor():
    conn = psycopg2.connect(database_url(), connect_timeout=8)
    conn.set_session(readonly=True, autocommit=True)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
    finally:
        conn.close()


def _rows(sql: str, params: tuple = ()) -> list[dict]:
    with _cursor() as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def _finite_amount(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return amount if math.isfinite(amount) else None


def _latest_reports(rows: list[dict]) -> list[dict]:
    """Keep one current version per store/day without changing stored history."""
    latest = {}
    for row in rows:
        key = (row["dealer_id"], row["report_date"])
        version = (_utc_iso(row.get("created_at")) or "", row.get("id") or 0)
        if key not in latest or version > latest[key][0]:
            latest[key] = (version, row)
    return [row for _, row in latest.values()]


def _store_ids_for_owner(owner_key: str) -> list[str]:
    """返回某 owner_key 名下的活跃门店 store_id（sales 角色范围）。"""
    if not owner_key:
        return []
    rows = _rows(
        "select store_id from dealer_stores where is_active = true and sales_owner = %s",
        (owner_key,),
    )
    return [r["store_id"] for r in rows]


# ── 门店 ───────────────────────────────────────────────────────────────────────

def list_stores(region: str = "", owner_key: str = "") -> list[dict]:
    sql = (
        "select store_id, name, region, country, dealer_level, sales_owner, team_key "
        "from dealer_stores where is_active = true"
    )
    params: list = []
    if owner_key:
        sql += " and sales_owner = %s"
        params.append(owner_key)
    if region:
        sql += " and region = %s"
        params.append(region)
    sql += " order by region, sort_order, store_id"
    return _rows(sql, tuple(params))


# ── Sell-in（经销商进货，CNY 万）──────────────────────────────────────────────

def sell_in_summary(month: str, owner_key: str = "") -> dict:
    params: list = [month + "%"]
    sql = (
        "select check_date, dealer_name, sell_in_wan, units, phone_qty, source_file, synced_at "
        "from dealer_sales where check_date like %s"
    )
    if owner_key:
        # dealer_sales 的客户名已脱敏，按该 owner 名下的门店名过滤（能匹配多少算多少）
        store_names = _rows(
            "select name from dealer_stores where is_active = true and sales_owner = %s",
            (owner_key,),
        )
        names = [r["name"] for r in store_names]
        sql += " and dealer_name = any(%s)"
        params.append(names)
    sql += " order by check_date desc"
    rows = _rows(sql, tuple(params))
    snapshot_date = max((row["check_date"] for row in rows), default=None)
    rows = [row for row in rows if row["check_date"] == snapshot_date]
    amounts = [_finite_amount(row["sell_in_wan"]) for row in rows]
    amount_state = "available" if rows else "missing"
    legacy_sources = {"vertu-cli:sales-orders", "sync_from_vertu"}
    if rows and (None in amounts or (
            all(amount == 0 for amount in amounts)
            and any(row["units"] != 0 for row in rows)
            and any(row.get("source_file") in legacy_sources for row in rows))):
        amount_state = "suspect"
    total_wan = round(sum(amounts), 2) if amount_state == "available" else None
    dealers = [dict(row, sell_in_wan=amount if amount_state == "available" else None,
                    synced_at=_utc_iso(row.get("synced_at")), amount_state=amount_state)
               for row, amount in zip(rows, amounts)]
    return {
        "month": month,
        "record_count": len(rows),
        "total_wan": total_wan,
        "dealers": dealers,
        "has_data": bool(rows),
        "snapshot_date": snapshot_date,
        "source": "dealer_sales_db_latest_snapshot",
        "as_of": max((row["synced_at"] for row in dealers if row["synced_at"]), default=None),
        "amount_state": amount_state,
        "amount_message": "快照金额缺失、无效，或旧来源存在销量但金额全零；金额待复核，销量和原始数据保留。" if amount_state == "suspect" else "",
    }


# ── Sell-out（门店五件套上报，USD）────────────────────────────────────────────

# 与看板一致：单条成交金额超过该 USD 阈值视为录入异常（货币单位错误），不计入汇总。
SELL_OUT_REVIEW_THRESHOLD_USD = 1_000_000


def sell_out_summary(month: str, owner_key: str = "") -> dict:
    rows = five_kit(month, owner_key=owner_key)
    valid = [row for row in rows if not row["amount_requires_review"]]
    total_usd = round(sum(row["deal_amount_usd"] for row in valid), 2) if valid else None
    excluded = len(rows) - len(valid)
    amount_state = "missing" if not rows else "suspect" if not valid else "partial" if excluded else "available"
    return {
        "month": month,
        "record_count": len(rows),
        "total_usd": total_usd,
        "excluded_record_count": excluded,
        "stores": rows,
        "has_data": bool(rows),
        "amount_state": amount_state,
        "source": "walkin_daily_reports_db_latest_submission",
        "as_of": max((row["created_at"] for row in rows if row["created_at"]), default=None),
        "amount_message": f"{excluded} 条金额待复核，未计入汇总。" if excluded else "",
    }


# ── 五件套明细（客流来源 + 成交漏斗）────────────────────────────────────────

def five_kit(month: str, dealer_id: str = "", owner_key: str = "") -> list[dict]:
    sql = (
        "select id, created_at, report_date, dealer_id, dealer_name, walkin_visits, cross_visits, "
        "online_visits, recruit_visits, existing_visits, touch_count, use_count, "
        "wechat_add_count, deal_count, deal_amount_yuan, notes, submitted_by "
        "from walkin_daily_reports where report_date like %s"
    )
    params: list = [month + "%"]
    if dealer_id:
        sql += " and dealer_id = %s"
        params.append(dealer_id)
    if owner_key:
        store_ids = _store_ids_for_owner(owner_key)
        if not store_ids or (dealer_id and dealer_id not in store_ids):
            return []
        sql += " and dealer_id = any(%s)"
        params.append(store_ids)
    sql += " order by report_date desc"
    rows = _latest_reports(_rows(sql, tuple(params)))
    result = []
    for row in rows:
        amount = _finite_amount(row["deal_amount_yuan"])
        requires_review = amount is None or not 0 <= amount <= SELL_OUT_REVIEW_THRESHOLD_USD
        result.append(dict(row, created_at=_utc_iso(row.get("created_at")),
                           deal_amount_usd=None if requires_review else amount,
                           amount_requires_review=requires_review))
    return result


# ── 会议 ───────────────────────────────────────────────────────────────────────

def meetings(date: str) -> list[dict]:
    return _rows(
        "select external_id, title, meeting_type, bucket, duration_minutes, brief, "
        "todos_json, participants_json from meeting_records "
        "where meeting_date = %s order by id",
        (date,),
    )


# ── 月度目标 ───────────────────────────────────────────────────────────────────

def monthly_targets(month: str) -> list[dict]:
    return _rows(
        "select month, dealer_id, sell_out_target_yuan, visit_target, deal_target, "
        "add_rate_target, created_by from monthly_targets where month = %s",
        (month,),
    )
