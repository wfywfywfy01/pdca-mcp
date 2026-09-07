"""Data-contract regressions; all records are synthetic and no database is used."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pdca_mcp import db


def sale(day="2026-08-31", amount=20, units=2, source="vertu-cli:sales-orders:validated"):
    return dict(check_date=day, dealer_name="fixture", sell_in_wan=amount,
                units=units, phone_qty=units, source_file=source,
                synced_at=datetime(2026, 9, 1, 8, tzinfo=timezone(timedelta(hours=8))))


def report(identifier=1, amount=40, submitted=None, day="2026-08-31", store="fixture"):
    return dict(id=identifier, report_date=day, dealer_id=store, dealer_name=store,
                deal_count=1, deal_amount_yuan=amount, created_at=submitted)


class DataIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.connection = patch.object(db.psycopg2, "connect", side_effect=AssertionError("No real DB in tests"))
        self.connection.start()
        self.addCleanup(self.connection.stop)

    def test_sell_in_uses_latest_month_snapshot_and_retains_returns(self):
        rows = [sale("2026-08-30", 10), sale(amount=20), sale(amount=-3, units=-1)]
        with patch.object(db, "_rows", return_value=rows):
            result = db.sell_in_summary("2026-08")
        self.assertEqual(result["total_wan"], 17)
        self.assertEqual(result["record_count"], 2)
        self.assertTrue(result["has_data"])
        self.assertEqual(result["snapshot_date"], "2026-08-31")
        self.assertEqual(result["amount_state"], "available")
        self.assertEqual(result["source"], "dealer_sales_db_latest_snapshot")
        self.assertTrue(result["as_of"].startswith("2026-09-01T00:00:00"))
        self.assertTrue(result["as_of"].endswith("+00:00"))

    def test_sell_in_verified_zero_is_available(self):
        with patch.object(db, "_rows", return_value=[sale(amount=0)]):
            result = db.sell_in_summary("2026-08")
        self.assertEqual(result["total_wan"], 0)
        self.assertEqual(result["amount_state"], "available")

    def test_sell_in_legacy_zero_with_units_is_suspect_without_previous_day_fallback(self):
        rows = [sale("2026-08-30", 10), sale(amount=0, units=703, source="vertu-cli:sales-orders")]
        with patch.object(db, "_rows", return_value=rows):
            result = db.sell_in_summary("2026-08")
        self.assertIsNone(result["total_wan"])
        self.assertEqual(result["amount_state"], "suspect")
        self.assertEqual(result["snapshot_date"], "2026-08-31")
        self.assertTrue(result["has_data"])
        self.assertEqual(result["dealers"][0]["units"], 703)
        self.assertIsNone(result["dealers"][0]["sell_in_wan"])
        self.assertEqual(rows[1]["sell_in_wan"], 0, "Raw records must not be rewritten")

    def test_sell_in_missing_or_invalid_amount_is_not_zero(self):
        for amount in (None, float("nan"), float("inf"), "redacted"):
            with self.subTest(amount=amount), patch.object(db, "_rows", return_value=[sale(amount=amount)]):
                result = db.sell_in_summary("2026-08")
                self.assertIsNone(result["total_wan"])
                self.assertEqual(result["amount_state"], "suspect")

    def test_sell_in_empty_scope_and_missing_snapshot_are_missing(self):
        for owner in ("", "fixture-owner"):
            with self.subTest(owner=owner), patch.object(db, "_rows", return_value=[]):
                result = db.sell_in_summary("2026-08", owner)
                self.assertIsNone(result["total_wan"])
                self.assertFalse(result["has_data"])
                self.assertEqual(result["amount_state"], "missing")
                self.assertIsNone(result["as_of"])

    def test_five_kit_latest_created_at_then_id_and_preserves_other_days(self):
        earlier = datetime(2026, 8, 31, 8)
        later = datetime(2026, 8, 31, 9, tzinfo=timezone.utc)
        rows = [report(9, 100, earlier), report(2, 80, later), report(3, 0, later),
                report(8, 90), report(10, 15, day="2026-08-30")]
        with patch.object(db, "_rows", return_value=rows):
            result = db.five_kit("2026-08")
        self.assertEqual({row["id"] for row in result}, {3, 10})
        self.assertEqual(next(row for row in result if row["id"] == 3)["deal_amount_yuan"], 0)
        self.assertEqual(len(rows), 5, "Historical rows must remain untouched")

    def test_sell_out_deduplicates_before_amount_review(self):
        rows = [report(1, 2_000_000, datetime(2026, 8, 31, 8)),
                report(2, 40, datetime(2026, 8, 31, 9))]
        with patch.object(db, "_rows", return_value=rows):
            result = db.sell_out_summary("2026-08")
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["total_usd"], 40)
        self.assertEqual(result["excluded_record_count"], 0)

    def test_sell_out_all_review_amounts_are_unavailable_and_marked(self):
        for amount in (2_000_000, None, float("nan"), -1):
            with self.subTest(amount=amount), patch.object(db, "_rows", return_value=[report(amount=amount)]):
                result = db.sell_out_summary("2026-08")
                self.assertIsNone(result["total_usd"])
                self.assertEqual(result["amount_state"], "suspect")
                self.assertEqual(result["excluded_record_count"], 1)
                self.assertTrue(result["stores"][0]["amount_requires_review"])
                self.assertIsNone(result["stores"][0]["deal_amount_usd"])

    def test_sell_out_mixed_amounts_are_partial_and_zero_is_valid(self):
        rows = [report(amount=0), report(2, 40, store="fixture-two"), report(3, 2_000_000, store="fixture-three")]
        with patch.object(db, "_rows", return_value=rows):
            result = db.sell_out_summary("2026-08")
        self.assertEqual(result["total_usd"], 40)
        self.assertEqual(result["amount_state"], "partial")
        self.assertEqual(result["excluded_record_count"], 1)
        with patch.object(db, "_rows", return_value=[report(amount=0)]):
            result = db.sell_out_summary("2026-08")
        self.assertEqual(result["total_usd"], 0)
        self.assertEqual(result["amount_state"], "available")

    def test_sell_out_no_records_or_no_owned_stores_are_missing(self):
        for owner in ("", "fixture-owner"):
            with self.subTest(owner=owner), patch.object(db, "_rows", return_value=[]):
                result = db.sell_out_summary("2026-08", owner)
                self.assertIsNone(result["total_usd"])
                self.assertEqual(result["amount_state"], "missing")
                self.assertFalse(result["has_data"])

    def test_five_kit_external_dealer_cannot_bypass_owner(self):
        with patch.object(db, "_store_ids_for_owner", return_value=["owned"]), patch.object(db, "_rows") as rows:
            self.assertEqual(db.five_kit("2026-08", "external", "fixture-owner"), [])
        rows.assert_not_called()

    def test_five_kit_owned_dealer_keeps_both_filters(self):
        with patch.object(db, "_store_ids_for_owner", return_value=["owned"]), patch.object(db, "_rows", return_value=[]) as rows:
            db.five_kit("2026-08", "owned", "fixture-owner")
        sql, params = rows.call_args.args
        self.assertIn("and dealer_id = %s", sql)
        self.assertIn("and dealer_id = any(%s)", sql)
        self.assertIn("owned", params)
        self.assertIn(["owned"], params)


if __name__ == "__main__":
    unittest.main()
