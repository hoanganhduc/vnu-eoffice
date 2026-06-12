"""Offline tests for direct document search/download/send helpers."""
import tempfile
import unittest
from pathlib import Path

from vnu_eoffice.documents import (
    DocumentRef,
    download_documents,
    fetch_documents,
    parse_document_refs,
    search_documents,
    send_documents,
)
from vnu_eoffice.models import Document


def doc(intid="1", module="den", has_attach=True):
    return Document(
        module=module,
        intid=intid,
        number=f"N{intid}",
        symbol=f"S{intid}",
        subject=f"Document {intid}",
        date="2026-06-12 00:00:00",
        party="Unit",
        has_attach=has_attach,
    )


class FakeClient:
    def __init__(self, docs_by_module, root=None):
        self.docs_by_module = docs_by_module
        self.root = Path(root) if root else None
        self.calls = []

    def list_documents(self, module, page=1, limit=20, search="", **extra):
        self.calls.append((module, page, limit, search, extra))
        docs = self.docs_by_module.get(module, [])
        if extra.get("intid"):
            docs = [d for d in docs if d.intid == str(extra["intid"])]
        start = (page - 1) * limit
        return len(docs), docs[start:start + limit]

    def download_all(self, document, dest_dir=None):
        if not document.has_attach:
            return []
        dest = Path(dest_dir) if dest_dir else self.root / document.module / document.intid
        dest.mkdir(parents=True, exist_ok=True)
        path = dest / f"{document.intid}.pdf"
        path.write_bytes(b"pdf")
        return [path]


class FakeNotifier:
    def __init__(self):
        self.messages = []
        self.documents = []

    def send_message(self, text):
        self.messages.append(text)
        return {"ok": True}

    def send_document(self, path, caption=""):
        self.documents.append((Path(path), caption))
        return {"ok": True}


class TestDocumentHelpers(unittest.TestCase):
    def test_parse_document_refs_accepts_defaults_prefixes_and_commas(self):
        refs = parse_document_refs(["1,2", "di:3"], default_module="den")
        self.assertEqual(refs, [
            DocumentRef("den", "1"),
            DocumentRef("den", "2"),
            DocumentRef("di", "3"),
        ])

    def test_search_documents_uses_keyword_query_per_module(self):
        client = FakeClient({"den": [doc("1")], "di": [doc("2", module="di")]})
        results = search_documents(client, "  hop   khan  ", modules=("den", "di"), limit=5)
        self.assertEqual([d.key for d in results], ["den:1", "di:2"])
        self.assertEqual(client.calls[0][3], "hop khan")
        self.assertEqual(client.calls[1][3], "hop khan")

    def test_fetch_documents_walks_multiple_pages(self):
        client = FakeClient({"den": [doc("1"), doc("2"), doc("3")]})
        total, results = fetch_documents(client, "den", limit=1, pages=3)
        self.assertEqual(total, 3)
        self.assertEqual([d.intid for d in results], ["1", "2", "3"])
        self.assertEqual([call[1] for call in client.calls], [1, 2, 3])

    def test_search_documents_uses_multiple_pages_by_default_arg(self):
        client = FakeClient({"den": [doc("1"), doc("2"), doc("3")]})
        results = search_documents(client, "doc", modules=("den",), limit=1, pages=2)
        self.assertEqual([d.intid for d in results], ["1", "2"])
        self.assertEqual([call[1] for call in client.calls], [1, 2])

    def test_download_documents_handles_multiple_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient({"den": [doc("1"), doc("2")]}, root=tmp)
            items = download_documents(client, [DocumentRef("den", "1"), DocumentRef("den", "2")])
            self.assertEqual([item.doc.intid for item in items], ["1", "2"])
            self.assertTrue(all(item.files[0].exists() for item in items))

    def test_send_documents_sends_message_and_files_then_deletes(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = FakeClient({"den": [doc("1")]}, root=tmp)
            notifier = FakeNotifier()
            items = send_documents(
                client,
                notifier,
                [DocumentRef("den", "1")],
                delete_after=True,
            )
            self.assertEqual(len(notifier.messages), 1)
            self.assertEqual(len(notifier.documents), 1)
            self.assertFalse(items[0].files[0].exists())


if __name__ == "__main__":
    unittest.main()
