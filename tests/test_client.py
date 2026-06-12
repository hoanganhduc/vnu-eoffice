"""Offline tests for endpoint parsing and attachment path handling."""
import tempfile
import unittest
from pathlib import Path

from vnu_eoffice import config
from vnu_eoffice.client import VnuApiError, VnuClient, _loads_lenient
from vnu_eoffice.models import Document


class Response:
    def __init__(self, text="{}", chunks=None):
        self.text = text
        self._chunks = chunks or []
        self.status_code = 200

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size=65536):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Session:
    def __init__(self, get_response=None, post_response=None):
        self.get_response = get_response or Response()
        self.post_response = post_response or Response()
        self.headers = {}

    def get(self, *args, **kwargs):
        return self.get_response

    def post(self, *args, **kwargs):
        return self.post_response


class TestLenientParsing(unittest.TestCase):
    def test_html_response_raises(self):
        with self.assertRaises(VnuApiError):
            _loads_lenient("<html><form>login</form></html>")

    def test_sELAB_envelope_parses(self):
        data = _loads_lenient('{ total : 1, results : [{"intid": "1"}] }')
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["results"][0]["intid"], "1")


class TestClientContracts(unittest.TestCase):
    def client_with(self, get_text="{}", post_text="[]"):
        client = VnuClient()
        client._logged_in = True
        client.session = Session(Response(get_text), Response(post_text))
        return client

    def test_list_documents_rejects_login_html(self):
        client = self.client_with(get_text="<html>login</html>")
        with self.assertRaises(VnuApiError):
            client.list_documents("den")

    def test_non_vnu_base_url_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "non-default base URL"):
            VnuClient(base_url="https://example.invalid/qlvb/")

    def test_attachments_accepts_results_envelope(self):
        client = self.client_with(post_text='{ total : 1, results : [{"name":"a.pdf","itemId":"42"}] }')
        self.assertEqual(client.attachments("den", "1"), [{"name": "a.pdf", "itemId": "42"}])

    def test_download_all_sanitizes_document_directory(self):
        client = VnuClient()
        client._logged_in = True
        client.attachments = lambda module, intid: [{"name": "a.pdf", "itemId": "42"}]
        client.download_file = lambda module, item_id, dest: Path(dest)
        doc = Document(
            module="den",
            intid="../123",
            number="../unsafe/number",
            symbol="",
            subject="",
            date="",
            party="",
        )
        old_docs_dir = config.DOCS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            config.DOCS_DIR = Path(tmp)
            try:
                [path] = client.download_all(doc)
            finally:
                config.DOCS_DIR = old_docs_dir
        self.assertNotIn("..", path.parts)
        self.assertTrue(any("_unsafe_number" in part for part in path.parts))


if __name__ == "__main__":
    unittest.main()
