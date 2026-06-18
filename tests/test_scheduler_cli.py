"""Offline tests for scheduler and CLI argument validation."""
import contextlib
import io
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

    def test_schedule_preview_has_no_importance_threshold(self):
        parser = build_parser()
        args = parser.parse_args(["schedule", "--preview"])

        with patch("vnu_eoffice.scheduler.preview", return_value="cron line") as preview, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(args.func(args), 0)

        monitor_args = preview.call_args.args[1]
        self.assertNotIn("--min-level", monitor_args)


class TestCliValidation(unittest.TestCase):
    def test_empty_modules_rejected(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["schedule", "--preview", "--modules", ""])

    def test_invalid_schedule_interval_rejected(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["schedule", "--preview", "--every", "0"])

    def test_search_command_parses_keywords(self):
        parser = build_parser()
        args = parser.parse_args(["search", "hop", "khan", "--modules", "den,di"])
        self.assertEqual(args.keywords, ["hop", "khan"])
        self.assertEqual(args.modules, ("den", "di"))
        self.assertEqual(args.pages, config.DEFAULT_FETCH_PAGES)

    def test_search_command_accepts_pages(self):
        parser = build_parser()
        args = parser.parse_args(["search", "hop", "--pages", "4"])
        self.assertEqual(args.pages, 4)

    def test_download_accepts_repeated_ids(self):
        parser = build_parser()
        args = parser.parse_args(["download", "--module", "den", "--id", "1", "--id", "di:2"])
        self.assertEqual(args.ids, ["1", "di:2"])

    def test_send_accepts_delete_after(self):
        parser = build_parser()
        args = parser.parse_args(["send", "--id", "den:1", "--delete-after"])
        self.assertEqual(args.ids, ["den:1"])
        self.assertTrue(args.delete_after)

    def test_score_command_is_removed(self):
        parser = build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["score", "hỏa tốc"])


if __name__ == "__main__":
    unittest.main()
