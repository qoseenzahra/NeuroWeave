from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx


class ConversationApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_pagination_validation_and_archived_delete_http_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.dict(os.environ, {
                "LOCALFLOW_DATABASE_PATH": str(root / "api.db"),
                "LOCALFLOW_OUTPUT_ROOT": str(root / "outputs"),
                "LOCALFLOW_EXECUTION_ENABLED": "false",
            }):
                main = importlib.import_module("app.main")
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=main.app), base_url="http://test",
                ) as client:
                    for index in range(23):
                        main.conversation_service.create(f"API 测试 {index}")
                    first = await client.get("/api/conversations")
                    self.assertEqual(first.status_code, 200)
                    page = first.json()
                    self.assertEqual(len(page["conversations"]), 20)
                    self.assertTrue(page["has_more"])
                    second = (await client.get("/api/conversations", params={
                        "cursor": page["next_cursor"],
                    })).json()
                    self.assertEqual(len(second["conversations"]), 3)
                    self.assertFalse(second["has_more"])
                    self.assertEqual((await client.get("/api/conversations", params={"cursor": "%%%"})).status_code, 422)
                    self.assertEqual((await client.get("/api/conversations", params={"limit": 500})).status_code, 422)
                    conversation_id = page["conversations"][0]["conversation_id"]
                    url = f"/api/conversations/{conversation_id}"
                    self.assertEqual((await client.delete(url)).status_code, 409)
                    self.assertEqual((await client.patch(url, json={"archived": True})).status_code, 200)
                    self.assertEqual((await client.delete(url)).status_code, 204)
                    self.assertEqual((await client.get(url)).status_code, 404)
                    self.assertEqual((await client.delete(url)).status_code, 404)
                    cors = await client.options(url, headers={
                        "Origin": "http://localhost:3000",
                        "Access-Control-Request-Method": "DELETE",
                    })
                    self.assertEqual(cors.status_code, 200)
            finally:
                main.run_service.shutdown()
                # This test imports app.main with a temporary database path.
                # Do not leave that process-wide module bound to a database that
                # TemporaryDirectory removes before later tests import app.main.
                sys.modules.pop("app.main", None)
                package = sys.modules.get("app")
                if package is not None and getattr(package, "main", None) is main:
                    delattr(package, "main")
