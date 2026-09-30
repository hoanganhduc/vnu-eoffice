"""Offline tests for the fail-closed retired notification interface."""
import unittest
from pathlib import Path

from vnu_eoffice.notify import TelegramError, TelegramNotifier, load_chat_id, save_chat_id


class TestTelegramNotifier(unittest.TestCase):
    def test_direct_notifier_construction_is_disabled(self):
        with self.assertRaisesRegex(TelegramError, "host delivery queue"):
            TelegramNotifier("untrusted-value", "untrusted-target")

    def test_config_construction_is_disabled(self):
        with self.assertRaisesRegex(TelegramError, "host delivery queue"):
            TelegramNotifier.from_config()

    def test_chat_discovery_and_persistence_are_disabled(self):
        self.assertIsNone(load_chat_id())
        with self.assertRaisesRegex(TelegramError, "host delivery queue"):
            save_chat_id("untrusted-target")

    def test_module_has_no_network_sender_or_token_discovery(self):
        source = (Path(__file__).parents[1] / "vnu_eoffice/notify.py").read_text()
        config = (Path(__file__).parents[1] / "vnu_eoffice/config.py").read_text()
        self.assertNotIn("requests", source)
        self.assertNotIn("api.telegram.org", source)
        self.assertNotIn("get_telegram_token", config)


if __name__ == "__main__":
    unittest.main()
