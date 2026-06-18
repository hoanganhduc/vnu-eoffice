"""Offline tests for numbered item mappings and package CLI integration."""
import contextlib
import io
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from vnu_eoffice import cli, config
from vnu_eoffice.documents import DocumentRef
from vnu_eoffice.items import (
    format_mapping_listing,
    load_mapping,
    resolve_document_refs,
    save_mapping,
)
from vnu_eoffice.models import Document


def doc(intid, module="den"):
    return Document(
        module=module,
        intid=str(intid),
        number=f"N{intid}",
        symbol=f"S{intid}",
        subject=f"Document {intid}",
        date=f"2026-06-{10 + int(intid):02d} 00:00:00",
        party="Unit",
        has_attach=True,
    )


class FakeClient:
    def __init__(self, docs_by_module):
        self.docs_by_module = docs_by_module

    def list_documents(self, module, page=1, limit=20, **kwargs):
        docs = self.docs_by_module.get(module, [])
        start = (page - 1) * limit
        return len(docs), docs[start:start + limit]


class FakeLogin:
    def __init__(self, client):
        self.client = client

    def login(self):
        return self.client


class TempItemsMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_items_file = config.ITEMS_FILE
        config.ITEMS_FILE = Path(self.tmp.name) / "last_items.json"

    def tearDown(self):
        config.ITEMS_FILE = self.old_items_file
        self.tmp.cleanup()


class TestItemMappings(TempItemsMixin, unittest.TestCase):
    def test_save_list_and_resolve_saved_item_numbers(self):
        docs = [doc(1, "den"), doc(2, "den"), doc(3, "di")]
        save_mapping("latest", docs, modules=("den", "di"))

        payload = load_mapping()
        text = format_mapping_listing(payload)

        self.assertIn("1. ID: den:1", text)
        self.assertIn("2. ID: den:2", text)
        self.assertIn("3. ID: di:3", text)
        self.assertEqual(
            resolve_document_refs(items=["2,3"], source="latest"),
            [DocumentRef("den", "2"), DocumentRef("di", "3")],
        )
        self.assertEqual(
            resolve_document_refs(ids=["den:1"], items=["1"], source="latest"),
            [DocumentRef("den", "1")],
        )

    def test_cli_list_prints_numbered_docs_and_saves_mapping(self):
        client = FakeClient({
            "den": [doc(1, "den")],
            "di": [doc(2, "di")],
        })
        args = types.SimpleNamespace(modules=("den", "di"), limit=20, pages=1)

        out = io.StringIO()
        with patch.object(cli, "VnuClient", return_value=FakeLogin(client)), \
             contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_list(args), 0)

        text = out.getvalue()
        self.assertIn("Use these item numbers for follow-up downloads.", text)
        self.assertIn("1. ID: den:1", text)
        self.assertIn("2. ID: di:2", text)
        saved = load_mapping("latest")
        self.assertEqual([item["key"] for item in saved["items"]], ["den:1", "di:2"])


if __name__ == "__main__":
    unittest.main()
