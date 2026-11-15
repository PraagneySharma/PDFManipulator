"""PDFManipulator data migration tests, using synthetic local-only state."""
from __future__ import annotations
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from studio.chatgpt import ChatGPTConnection
from studio.recipes import preset, read_recipes, store_path


class RenameStorageTests(unittest.TestCase):
    def test_recipe_migration_preserves_saved_workflows(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            old = root / "PDFWorkflowStudio" / "recipes.json"
            old.parent.mkdir(parents=True)
            example = preset("Split Every N Pages")
            old.write_text(json.dumps([example]), encoding="utf-8")
            with patch.dict(os.environ, {"APPDATA": str(root)}):
                new_location = store_path()
                self.assertEqual(new_location, root / "PDFManipulator" / "recipes.json")
                self.assertEqual(read_recipes(), {example["name"]: example})
                self.assertTrue(old.exists())
                self.assertTrue(new_location.exists())

    def test_chatgpt_migration_retains_host_identity_and_protected_tokens(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            old_location = root / "PDFWorkflowStudio" / "chatgpt"
            old = ChatGPTConnection(old_location)
            old_host = old.store.host_id
            old.store.upsert({
                "id": "test-account",
                "email": "tester@example.com",
                "subject": "test-subject",
                "issuer": "https://auth.openai.com",
                "client_id": "oaiapp_mock",
                "refresh_token": "synthetic-refresh-for-unit-testing",
                "access_token": "synthetic-access-for-unit-testing",
                "scopes": ["chatgpt.tokens.use.direct"],
                "expires_at": 9999999999,
                "model": "gpt-test"
            })
            with patch.dict(os.environ, {"LOCALAPPDATA": str(root)}):
                renamed = ChatGPTConnection()
                self.assertEqual(renamed.store.host_id, old_host)
                self.assertTrue(renamed.session()["sharing"])
                self.assertEqual(renamed.session()["email"], "tester@example.com")
                self.assertNotIn(b"synthetic-refresh", renamed.store.data_path.read_bytes())
                self.assertTrue(old.store.data_path.exists())
                # Migrating a second time does not replace existing settings.
                again = ChatGPTConnection()
                self.assertEqual(again.store.host_id, old_host)


if __name__ == "__main__":
    unittest.main()
