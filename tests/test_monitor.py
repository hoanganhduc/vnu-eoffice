"""Offline tests for monitor state, retries, and cleanup."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vnu_eoffice import config
from vnu_eoffice.models import Document
from vnu_eoffice.monitor import HASHED_SEEN_PREFIX, _handle_alert, load_seen, run_once, save_seen


def doc(intid="1", subject="hỏa tốc", module="den"):
    return Document(
        module=module,
        intid=intid,
        number="1",
        symbol="S",
        subject=subject,
        date="2026-06-12 00:00:00",
        party="",
        has_attach=True,
    )


class FakeClient:
    def __init__(self, docs_by_module=None, fail_modules=()):
        self.docs_by_module = docs_by_module or {}
        self.fail_modules = set(fail_modules)
        self.calls = []

    def list_documents(self, module, page=1, limit=60, **kw):
        self.calls.append((module, page, limit, kw))
        if module in self.fail_modules:
            raise RuntimeError("list failed")
        docs = self.docs_by_module.get(module, [])
        start = (page - 1) * limit
        return len(docs), docs[start:start + limit]


class FailingNotifier:
    def send_message(self, *args, **kwargs):
        raise RuntimeError("send failed")


class OkNotifier:
    def send_message(self, *args, **kwargs):
        return {"ok": True}


class TempConfigMixin:
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old = (
            config.DATA_DIR,
            config.STATE_DIR,
            config.DOCS_DIR,
            config.SEEN_FILE,
            config.TELEGRAM_STATE_FILE,
        )
        config.DATA_DIR = root
        config.STATE_DIR = root / "state"
        config.DOCS_DIR = root / "documents"
        config.SEEN_FILE = config.STATE_DIR / "seen.json"
        config.TELEGRAM_STATE_FILE = config.STATE_DIR / "telegram.json"

    def tearDown(self):
        (
            config.DATA_DIR,
            config.STATE_DIR,
            config.DOCS_DIR,
            config.SEEN_FILE,
            config.TELEGRAM_STATE_FILE,
        ) = self.old
        self.tmp.cleanup()


class TestMonitorState(TempConfigMixin, unittest.TestCase):
    def test_failed_alert_is_not_marked_seen(self):
        save_seen({"_initialized_modules": ["den"], "den": []})
        result = run_once(
            modules=("den",),
            min_level="LOW",
            client=FakeClient({"den": [doc("1")]}),
            notifier=FailingNotifier(),
            notify=True,
        )
        self.assertEqual(len(result.errors), 1)
        self.assertEqual(load_seen()["den"], [])

    def test_successful_alert_is_marked_seen(self):
        save_seen({"_initialized_modules": ["den"], "den": []})
        result = run_once(
            modules=("den",),
            min_level="LOW",
            client=FakeClient({"den": [doc("1")]}),
            notifier=OkNotifier(),
            notify=True,
        )
        self.assertFalse(result.errors)
        self.assertEqual(load_seen()["den"], ["1"])

    def test_first_run_initializes_only_successful_modules(self):
        result = run_once(
            modules=("den", "di"),
            client=FakeClient({"den": [doc("1", module="den")]}, fail_modules=("di",)),
            notify=False,
        )
        state = load_seen()
        self.assertEqual(result.baseline_modules, ["den"])
        self.assertEqual(state["_initialized_modules"], ["den"])
        self.assertNotIn("di", state)

    def test_empty_modules_rejected(self):
        with self.assertRaises(ValueError):
            run_once(modules=(), client=FakeClient(), notify=False)

    def test_monitor_fetches_multiple_pages(self):
        save_seen({"_initialized_modules": ["den"], "den": []})
        client = FakeClient({"den": [doc("1"), doc("2")]})
        result = run_once(
            modules=("den",),
            limit=1,
            pages=2,
            min_level="LOW",
            client=client,
            notifier=OkNotifier(),
            notify=True,
        )
        self.assertFalse(result.errors)
        self.assertEqual(result.new_count, 2)
        self.assertEqual([call[1] for call in client.calls], [1, 2])

    def test_hashed_seen_state_does_not_store_raw_document_ids(self):
        with patch.dict(
            "os.environ",
            {"VNU_HASH_SEEN_IDS": "1", "VNU_STATE_HMAC_KEY": "test-key"},
        ):
            result = run_once(
                modules=("den",),
                client=FakeClient({"den": [doc("123456")]}),
                notify=False,
            )
            self.assertEqual(result.baseline_modules, ["den"])
            state = load_seen()
            self.assertEqual(len(state["den"]), 1)
            self.assertTrue(state["den"][0].startswith(HASHED_SEEN_PREFIX))
            self.assertNotIn("123456", config.SEEN_FILE.read_text())

            result = run_once(
                modules=("den",),
                client=FakeClient({"den": [doc("123456")]}),
                notify=False,
            )
            self.assertEqual(result.new_count, 0)


class TestAlertCleanup(unittest.TestCase):
    def test_delete_after_cleans_up_when_send_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "doc.pdf"
            path.write_bytes(b"pdf")

            class DownloadingClient:
                def download_all(self, document):
                    return [path]

            with self.assertRaises(RuntimeError):
                _handle_alert(
                    DownloadingClient(),
                    FailingNotifier(),
                    doc("1"),
                    score=type("Score", (), {
                        "emoji": "x",
                        "level": "HIGH",
                        "value": 10,
                        "reasons": [],
                        "deadline_hint": "",
                    })(),
                    download=True,
                    delete_after=True,
                    send_files=False,
                    dry_run=False,
                    require_delivery=True,
                )
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
