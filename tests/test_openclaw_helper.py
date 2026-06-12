"""Offline tests for the OpenClaw VNU eOffice adapter helper."""
import contextlib
import importlib.util
import io
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from vnu_eoffice import config
from vnu_eoffice.models import Document


HELPER_PATH = Path(__file__).resolve().parents[1] / "openclaw" / "vnu_eoffice" / "vnu_eoffice_openclaw.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("vnu_eoffice_openclaw_test", HELPER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def doc(intid, module):
    return Document(
        module=module,
        intid=str(intid),
        number=f"N{intid}",
        symbol=f"S{intid}",
        subject=f"Document {intid}",
        date=f"2026-06-{12 - int(intid):02d} 00:00:00",
        party="Unit",
        has_attach=True,
    )


class FakeClient:
    def __init__(self, docs_by_module):
        self.docs_by_module = docs_by_module

    def list_documents(self, module, page=1, limit=20, **kwargs):
        docs = self.docs_by_module[module]
        start = (page - 1) * limit
        return len(docs), docs[start:start + limit]


class FakeLogin:
    def __init__(self, client):
        self.client = client

    def login(self):
        return self.client


class FakeNotifier:
    def __init__(self):
        self.messages = []

    def send_message(self, text):
        self.messages.append(text)


class TestOpenClawHelper(unittest.TestCase):
    def test_default_fetch_pages_is_two(self):
        helper = load_helper()
        self.assertEqual(config.DEFAULT_FETCH_PAGES, 2)
        parser = helper.build_parser()

        latest = parser.parse_args(["latest"])
        search = parser.parse_args(["search", "--query", "hop"])
        monitor = parser.parse_args(["monitor"])

        self.assertEqual(latest.pages, 2)
        self.assertEqual(search.pages, 2)
        self.assertEqual(monitor.pages, 2)

    def test_latest_limit_is_display_count_not_pages_times_limit(self):
        helper = load_helper()
        client = FakeClient({
            "den": [doc(1, "den"), doc(2, "den"), doc(3, "den")],
            "di": [doc(1, "di"), doc(2, "di"), doc(3, "di")],
        })
        args = types.SimpleNamespace(
            modules="den,di",
            limit=2,
            pages=2,
            send_telegram=False,
        )

        out = io.StringIO()
        with patch.object(helper, "VnuClient", return_value=FakeLogin(client)), \
             patch.object(helper, "save_mapping") as save_mapping, \
             contextlib.redirect_stdout(out):
            self.assertEqual(helper.cmd_latest(args), 0)

        text = out.getvalue()
        self.assertIn("Task: VNU eOffice latest documents", text)
        self.assertIn("Latest documents - showing up to 2 per category; scanned 2 page(s).", text)
        self.assertIn("Scan", text)
        self.assertIn("Follow-up", text)
        self.assertIn("1. ID: den:1", text)
        self.assertIn("2. ID: den:2", text)
        self.assertNotIn("den:3", text)
        self.assertIn("3. ID: di:1", text)
        self.assertIn("4. ID: di:2", text)
        self.assertNotIn("di:3", text)
        saved_docs = save_mapping.call_args.args[1]
        self.assertEqual([item.key for item in saved_docs], ["den:1", "den:2", "di:1", "di:2"])

    def test_send_plain_text_strips_duplicate_title_before_notifier(self):
        helper = load_helper()
        notifier = FakeNotifier()

        with patch.object(helper, "titled_notifier", return_value=notifier):
            helper.send_plain_text("Task: VNU eOffice latest documents\n\nBody", "Task: VNU eOffice latest documents")

        self.assertEqual(notifier.messages, ["Body"])


if __name__ == "__main__":
    unittest.main()
