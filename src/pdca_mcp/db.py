# -*- coding: utf-8 -*-
"""只读查询生产 PostgreSQL。所有查询均不加任何写锁，只 SELECT。"""
from __future__ import annotations

from contextlib import contextmanager

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
        "select check_date, dealer_name, sell_in_wan, units, phone_qty "
        "from dealer_sales where check_date like %s"
    )
    if owner_key:
        # dealer_sales 的客户名已脱敏，按该 owner 名下的门店名过滤（能匹配多少算多少）
        store_names = _rows(
            "select name from dealer_stores where is_active = true and sales_owner = %s",
            (owner_key,),
        )
        names = [r["name"] for r in store_names]
        if not names:
            return {"month": month, "record_count": 0, "total_wan": 0.0, "dealers": []}
        sql += " and dealer_name = any(%s)"
        params.append(names)
    sql += " order by check_date desc"
    rows = _rows(sql, tuple(params))
    total_wan = round(sum(float(r["sell_in_wan"] or 0) for r in rows), 2)
    return {
        "month": month,
        "record_count": len(rows),
        "total_wan": total_wan,
        "dealers": rows,
    }


# ── Sell-out（门店五件套上报，USD）────────────────────────────────────────────

# 与看板一致：单条成交金额超过该 USD 阈值视为录入异常（货币单位错误），不计入汇总。
SELL_OUT_REVIEW_THRESHOLD_USD = 1_000_000


def sell_out_summary(month: str, owner_key: str = "") -> dict:
    params: list = [month + "%"]
    sql = (
        "select report_date, dealer_id, dealer_name, deal_count, deal_amount_yuan "
        "from walkin_daily_reports where report_date like %s"
    )
    if owner_key:
        store_ids = _store_ids_for_owner(owner_key)
        if not store_ids:
            return {"month": month, "record_count": 0, "total_usd": 0.0, "excluded_record_count": 0, "stores": []}
        sql += " and dealer_id = any(%s)"
        params.append(store_ids)
    sql += " order by report_date desc"
    rows = _rows(sql, tuple(params))
    valid = [r for r in rows if float(r["deal_amount_yuan"] or 0) <= SELL_OUT_REVIEW_THRESHOLD_USD]
    total_usd = round(sum(float(r["deal_amount_yuan"] or 0) for r in valid), 2)
    excluded = len(rows) - len(valid)
    return {
        "month": month,
        "record_count": len(rows),
        "total_usd": total_usd,
        "excluded_record_count": excluded,
        "stores": rows,
    }


# ── 五件套明细（客流来源 + 成交漏斗）────────────────────────────────────────

def five_kit(month: str, dealer_id: str = "", owner_key: str = "") -> list[dict]:
    sql = (
        "select report_date, dealer_id, dealer_name, walkin_visits, cross_visits, "
        "online_visits, recruit_visits, existing_visits, touch_count, use_count, "
        "wechat_add_count, deal_count, deal_amount_yuan, notes, submitted_by "
        "from walkin_daily_reports where report_date like %s"
    )
    params: list = [month + "%"]
    if dealer_id:
        sql += " and dealer_id = %s"
        params.append(dealer_id)
    elif owner_key:
        store_ids = _store_ids_for_owner(owner_key)
        if not store_ids:
            return []
        sql += " and dealer_id = any(%s)"
        params.append(store_ids)
    sql += " order by report_date desc"
    return _rows(sql, tuple(params))


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
