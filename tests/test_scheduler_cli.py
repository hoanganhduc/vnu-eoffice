"""Offline tests for scheduler and CLI argument validation."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from vnu_eoffice import config, scheduler
from vnu_eoffice.cli import build_parser


class TestScheduler(unittest.TestCase):
    def test_invalid_intervals_rejected(self):
        for value in (0, -5, 90):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    scheduler.validate_interval(value)

    def test_preview_does_not_create_runtime_dirs(self):
        old_data_dir = config.DATA_DIR
        with tempfile.TemporaryDirectory() as tmp:
            config.DATA_DIR = Path(tmp) / "data"
            try:
                line = scheduler.preview(15, "monitor --once")
                self.assertIn("*/15", line)
                self.assertFalse(config.DATA_DIR.exists())
            finally:
                config.DATA_DIR = old_data_dir

    def test_windows_remove_uses_schtasks_delete(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            return type("Run", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        with patch("vnu_eoffice.scheduler.platform.system", return_value="Windows"), \
             patch("vnu_eoffice.scheduler.subprocess.run", side_effect=fake_run):
            self.assertTrue(scheduler.remove())
        self.assertEqual(calls[0][:3], ["schtasks", "/Delete", "/TN"])


class TestCliValidation(unittest.TestCase):
    def test_empty_modules_rejected(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["schedule", "--preview", "--modules", ""])

    def test_invalid_schedule_interval_rejected(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["schedule", "--preview", "--every", "0"])


if __name__ == "__main__":
    unittest.main()
