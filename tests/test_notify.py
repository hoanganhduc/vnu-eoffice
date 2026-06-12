"""Offline tests for Telegram response handling."""
import unittest
from unittest.mock import patch

import requests

from vnu_eoffice.notify import TelegramError, TelegramNotifier


class Response:
    def __init__(self, data=None, http_error=None, json_error=None):
        self.data = data if data is not None else {"ok": True, "result": {}}
        self.http_error = http_error
        self.json_error = json_error

    def raise_for_status(self):
        if self.http_error:
            raise self.http_error

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.data


class TestTelegramNotifier(unittest.TestCase):
    def test_ok_false_raises(self):
        with patch("vnu_eoffice.notify.requests.post",
                   return_value=Response({"ok": False, "description": "Bad Request"})):
            with self.assertRaisesRegex(TelegramError, "Bad Request"):
                TelegramNotifier("token", "chat").send_message("hello")

    def test_http_error_raises(self):
        err = requests.HTTPError("boom")
        with patch("vnu_eoffice.notify.requests.post", return_value=Response(http_error=err)):
            with self.assertRaisesRegex(TelegramError, "request failed"):
                TelegramNotifier("token", "chat").send_message("hello")


if __name__ == "__main__":
    unittest.main()
