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


# ── 门店 ───────────────────────────────────────────────────────────────────────

def list_stores(region: str = "") -> list[dict]:
    sql = (
        "select store_id, name, region, country, dealer_level, sales_owner, team_key "
        "from dealer_stores where is_active = true"
    )
    params: tuple = ()
    if region:
        sql += " and region = %s"
        params = (region,)
    sql += " order by region, sort_order, store_id"
    return _rows(sql, params)


# ── Sell-in（经销商进货，CNY 万）──────────────────────────────────────────────

def sell_in_summary(month: str) -> dict:
    rows = _rows(
        "select check_date, dealer_name, sell_in_wan, units, phone_qty "
        "from dealer_sales where check_date like %s order by check_date desc",
        (month + "%",),
    )
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


def sell_out_summary(month: str) -> dict:
    rows = _rows(
        "select report_date, dealer_id, dealer_name, deal_count, deal_amount_yuan "
        "from walkin_daily_reports where report_date like %s order by report_date desc",
        (month + "%",),
    )
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

def five_kit(month: str, dealer_id: str = "") -> list[dict]:
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
