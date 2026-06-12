"""Offline unit tests for the local importance scorer (no network)."""
import unittest

from vnu_eoffice.importance import score_text
from vnu_eoffice.models import Document


class TestScoring(unittest.TestCase):
    def test_urgent_with_deadline_is_high(self):
        sc = score_text("Văn bản hỏa tốc, đề nghị báo cáo trước ngày 15/06/2026")
        self.assertEqual(sc.level, "HIGH")
        self.assertGreaterEqual(sc.value, 8)
        self.assertTrue(sc.deadline_hint)
        self.assertIn("15/06/2026", sc.deadline_hint)

    def test_meeting_invite_is_at_least_medium(self):
        sc = score_text("Giấy mời họp Hội đồng tuyển sinh")
        self.assertTrue(sc.meets("MEDIUM"))

    def test_routine_is_low(self):
        sc = score_text("Gia hạn thời gian thực hiện đề tài mã số 104.04")
        # "gia hạn" is routine; must not be inflated to HIGH.
        self.assertNotEqual(sc.level, "HIGH")

    def test_important_sender_boost(self):
        weak = score_text("Về việc cập nhật thông tin")
        strong = score_text("Về việc cập nhật thông tin", party="Thủ tướng Chính phủ")
        self.assertGreater(strong.value, weak.value)

    def test_reasons_are_reported(self):
        sc = score_text("Đề nghị góp ý dự thảo")
        self.assertTrue(sc.reasons)
        self.assertTrue(any("Yêu cầu xử lý" in r for r in sc.reasons))

    def test_meets_threshold_order(self):
        sc = score_text("hỏa tốc")
        self.assertTrue(sc.meets("LOW"))
        self.assertTrue(sc.meets("HIGH"))


class TestModelNormalisation(unittest.TestCase):
    def test_outgoing_party_falls_back_to_signer(self):
        rec = {"intid": "1", "strKyhieu": "9/X", "strTrichyeu": "abc",
               "strNgayky": "2026-06-12 00:00:00", "intSophathanh": "9",
               "strNoinhan": "", "strNguoiky": "Trần Quốc Bình", "attach": "1",
               "statusopen": "0"}
        d = Document.from_record("di", rec)
        self.assertEqual(d.number, "9")
        self.assertTrue(d.has_attach)
        self.assertTrue(d.unread)
        self.assertIn("Trần Quốc Bình", d.party)

    def test_subject_whitespace_collapsed(self):
        rec = {"intid": "2", "strTrichyeu": "dòng 1\r\ndòng 2", "intSoden": "3",
               "strKyhieu": "k", "strNgayden": "2026-06-12 09:00:00",
               "strCoquanphathanh": "X", "attach": "0", "statusopen": "1"}
        d = Document.from_record("den", rec)
        self.assertEqual(d.subject, "dòng 1 dòng 2")
        self.assertFalse(d.unread)


if __name__ == "__main__":
    unittest.main()
