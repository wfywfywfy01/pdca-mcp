"""Authentication regressions; all keys and records are synthetic, no database."""
import ast
import json
import unittest
from contextlib import ExitStack
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient
from starlette.responses import JSONResponse

from pdca_mcp import server


AUTH = {
    "unit-admin": {"role": "admin", "owner_key": ""},
    "unit-viewer": {"role": "viewer", "owner_key": ""},
    "unit-sales": {"role": "sales", "owner_key": "UnitSales"},
    "unit-other": {"role": "sales", "owner_key": "OtherSales"},
    "unit-dealer": {"role": "dealer", "owner_key": "UnitStore"},
    "unit-empty": {"role": "sales", "owner_key": "  "},
    "unit-unknown-role": {"role": "unknown", "owner_key": ""},
}


def context(authorization):
    return SimpleNamespace(request_context=SimpleNamespace(
        request=SimpleNamespace(headers={"authorization": authorization})))


def response_payload(response):
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    for line in response.text.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError("MCP response contained no JSON payload")


class ScopeSecurityTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(server.config, "api_key_auth", return_value=AUTH))
        self.stack.enter_context(patch.object(server, "_HTTP_MODE", True, create=True))
        self.stack.enter_context(patch.object(server.db.psycopg2, "connect", side_effect=AssertionError("Database access forbidden in security tests")))

    def test_http_missing_unknown_malformed_identity_never_becomes_admin(self):
        for header in ("", "Bearer unknown", "unit-admin", "Basic unit-admin", "Bearer unit-empty", "Bearer unit-unknown-role"):
            with self.subTest(header=header), self.assertRaises(PermissionError):
                server._owner_scope(context(header))

    def test_http_missing_context_fails_closed(self):
        for ctx in (None, SimpleNamespace(request_context=SimpleNamespace(request=None)), SimpleNamespace()):
            with self.subTest(ctx=ctx), self.assertRaises(PermissionError):
                server._owner_scope(ctx)

    def test_explicit_roles_preserve_scope(self):
        for key, expected in (("unit-admin", ""), ("unit-viewer", ""), ("unit-sales", "UnitSales"), ("unit-dealer", "UnitStore")):
            with self.subTest(key=key):
                self.assertEqual(server._owner_scope(context("Bearer " + key)), expected)

    def test_trusted_stdio_keeps_unrestricted_contract(self):
        with patch.object(server, "_HTTP_MODE", False, create=True):
            self.assertEqual(server._owner_scope(None), "")
            self.assertEqual(server._owner_scope(SimpleNamespace(request_context=SimpleNamespace(request=None))), "")

    def test_global_tools_refuse_scoped_callers_before_database(self):
        for name, arg in (("query_meetings", "2026-09-01"), ("query_monthly_targets", "2026-09")):
            for key in ("unit-sales", "unit-dealer"):
                with self.subTest(tool=name, key=key), self.assertRaises(PermissionError):
                    getattr(server, name)(arg, ctx=context("Bearer " + key))

    def test_global_tools_keep_admin_viewer_and_stdio_access(self):
        for name, database, arg in (("query_meetings", "meetings", "2026-09-01"), ("query_monthly_targets", "monthly_targets", "2026-09")):
            with patch.object(server.db, database, return_value=[]) as query:
                for key in ("unit-admin", "unit-viewer"):
                    self.assertEqual(getattr(server, name)(arg, ctx=context("Bearer " + key))["count"], 0)
                with patch.object(server, "_HTTP_MODE", False, create=True):
                    self.assertEqual(getattr(server, name)(arg)["count"], 0)
                self.assertEqual(query.call_count, 3)

    def test_invalid_dates_never_reach_database(self):
        for name, database in (("query_sell_in", "sell_in_summary"), ("query_sell_out", "sell_out_summary"), ("query_five_kit", "five_kit"), ("query_monthly_targets", "monthly_targets")):
            with patch.object(server.db, database) as query:
                for month in ("2026-9", "2026-%", "2026-00", "2026-13", "0000-01", "2026-09-01"):
                    with self.subTest(tool=name, month=month), self.assertRaises(ValueError):
                        getattr(server, name)(month, ctx=context("Bearer unit-admin"))
                query.assert_not_called()
        with patch.object(server.db, "meetings") as query:
            for day in ("20260901", "2026-02-30", "2026-%-01"):
                with self.subTest(day=day), self.assertRaises(ValueError):
                    server.query_meetings(day, ctx=context("Bearer unit-admin"))
            query.assert_not_called()

    def test_legacy_e2e_never_embeds_database_or_remote_key_credentials(self):
        for path in Path(__file__).parent.glob("e2e_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str):
                    self.assertFalse(node.value.startswith(("postgresql://", "postgres://")), path.name)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                    self.assertNotEqual(node.func.id, "eval", path.name)
                    if path.name == "e2e_remote.py" and node.func.id == "call" and node.args:
                        if isinstance(node.args[0], ast.Constant):
                            self.assertEqual(node.args[0].value, "wrong-key", "Remote credentials must come from explicit test settings")


class HttpSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        cls.stack.enter_context(patch.object(server.config, "api_key_auth", return_value=AUTH))
        cls.stack.enter_context(patch.object(server.db.psycopg2, "connect", side_effect=AssertionError("Database access forbidden in security tests")))
        cls.stack.enter_context(patch.object(server.db, "list_stores", side_effect=lambda region, owner: [{"scope": owner}]))
        cls.stack.enter_context(patch.object(server.db, "meetings", return_value=[]))
        cls.stack.enter_context(patch.object(server.db, "monthly_targets", return_value=[]))
        # One fresh FastMCP per suite; no private lifecycle state manipulation.
        mcp = FastMCP("pdca-auth-unit", json_response=True)
        for name in ("query_stores", "query_meetings", "query_monthly_targets"):
            mcp.tool()(getattr(server, name))
        cls.stack.enter_context(patch.object(server, "mcp", mcp))
        cls.client = cls.stack.enter_context(TestClient(server.build_http_app(), base_url="http://localhost:8765"))

    @classmethod
    def tearDownClass(cls):
        cls.stack.close()

    def headers(self, key=None, session=None):
        result = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
        if key is not None:
            result["Authorization"] = "Bearer " + key
        if session:
            result["mcp-session-id"] = session
        return result

    def post(self, method, key=None, session=None, params=None):
        return self.client.post("/mcp", headers=self.headers(key, session), json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})

    def initialize(self, key="unit-admin"):
        response = self.post("initialize", key, params={"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "unit", "version": "1"}})
        self.assertEqual(response.status_code, 200)
        session = response.headers["mcp-session-id"]
        self.addCleanup(lambda: self.client.delete("/mcp", headers=self.headers(key, session)))
        self.client.post("/mcp", headers=self.headers(key, session), json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        return session

    def test_missing_unknown_or_fake_session_is_401(self):
        for key, session in ((None, None), ("unknown", None), (None, "unit-fake-session"), ("unknown", "unit-fake-session")):
            with self.subTest(key=key, session=session):
                self.assertEqual(self.post("tools/list", key, session).status_code, 401)

    def test_empty_auth_configuration_does_not_open_http(self):
        async def allowed(scope, receive, send):
            await JSONResponse({"ok": True})(scope, receive, send)
        with patch.object(server.config, "api_key_auth", return_value={}):
            client = TestClient(server._auth_middleware(allowed))
            self.assertEqual(client.post("/mcp").status_code, 401)
            client.close()

    def test_removed_key_cannot_reuse_its_session(self):
        session = self.initialize()
        with patch.object(server.config, "api_key_auth", return_value={"unit-sales": AUTH["unit-sales"]}):
            self.assertEqual(self.post("tools/list", "unit-admin", session).status_code, 401)

    def test_valid_session_still_requires_valid_bearer(self):
        session = self.initialize()
        for key in (None, "unknown", "unit-empty", "unit-unknown-role"):
            with self.subTest(key=key):
                self.assertEqual(self.post("tools/list", key, session).status_code, 401)
        self.assertEqual(self.post("tools/list", "unit-admin", session).status_code, 200)

    def test_bearer_scheme_required_and_duplicate_headers_rejected(self):
        headers = self.headers()
        headers["Authorization"] = "unit-admin"
        response = self.client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(response.status_code, 401)
        duplicate = list(self.headers().items()) + [("Authorization", "Bearer unit-admin"), ("Authorization", "Bearer unit-sales")]
        self.assertEqual(self.client.post("/mcp", headers=duplicate, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).status_code, 401)

    def test_session_reuse_uses_current_callers_scope(self):
        session = self.initialize("unit-admin")
        for key, expected in (("unit-sales", "UnitSales"), ("unit-other", "OtherSales"), ("unit-admin", "")):
            response = self.post("tools/call", key, session, {"name": "query_stores", "arguments": {}})
            self.assertEqual(response.status_code, 200)
            result = response_payload(response)["result"]
            self.assertFalse(result.get("isError"))
            value = json.loads(result["content"][0]["text"])
            self.assertEqual(value["stores"], [{"scope": expected}])

    def test_global_tools_deny_sales_even_on_admin_session(self):
        session = self.initialize("unit-admin")
        for tool, arguments in (("query_meetings", {"date": "2026-09-01"}), ("query_monthly_targets", {"month": "2026-09"})):
            result = response_payload(self.post("tools/call", "unit-sales", session, {"name": tool, "arguments": arguments}))["result"]
            self.assertTrue(result.get("isError"))
            admin = response_payload(self.post("tools/call", "unit-viewer", session, {"name": tool, "arguments": arguments}))["result"]
            self.assertFalse(admin.get("isError"))


if __name__ == "__main__":
    unittest.main()
