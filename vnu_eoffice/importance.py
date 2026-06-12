"""Fully-local importance scoring for Vietnamese administrative documents.

No external services are contacted. Scoring is keyword/sender/deadline based and
fully transparent: every point added is reported with the phrase that caused it,
so a human can audit and tune the rules.

Matching is done on the lowercased subject WITH diacritics preserved, because
official Vietnamese text is consistently diacritised and folding would collide
distinct words (e.g. họp "meeting" vs hợp "combine"). Prefer multi-word phrases
over bare words to avoid false positives (e.g. "thời hạn" not bare "hạn").
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .models import Document

# category -> {phrase: weight}.  Category name is shown in the alert "reasons".
RULES: dict[str, dict[str, int]] = {
    "Khẩn": {
        "hỏa tốc": 10, "thượng khẩn": 9, "khẩn cấp": 8, "khẩn trương": 5,
        "khẩn": 6, "gấp": 4,
    },
    "Hạn chót": {
        "trước ngày": 4, "chậm nhất": 4, "hạn nộp": 4, "hạn cuối": 4,
        "thời hạn": 3, "đúng hạn": 2, "quá hạn": 3, "deadline": 4,
        "trước 17": 2, "trước 16": 2, "trước 11": 2,
    },
    "Yêu cầu xử lý": {
        "đề nghị": 3, "yêu cầu": 3, "xin ý kiến": 3, "cho ý kiến": 3,
        "góp ý": 3, "báo cáo": 2, "triển khai": 2, "tổ chức thực hiện": 2,
        "phối hợp": 1,
    },
    "Họp / Mời": {
        "giấy mời": 4, "kính mời": 3, "cuộc họp": 3, "hội nghị": 2,
        "hội thảo": 2, "tập huấn": 2, "làm việc": 1, "họp": 2,
    },
    "Loại văn bản": {
        "chỉ thị": 3, "nghị quyết": 2, "quyết định": 2, "kế hoạch": 1,
        "thông báo": 1,
    },
    "Nơi gửi quan trọng": {
        "thủ tướng": 5, "chính phủ": 4, "bộ giáo dục": 3, "bộ gd": 3,
        "cơ quan đhqghn": 3, "đảng ủy": 3, "ban giám đốc": 3, "đhqghn": 2,
        "giám đốc": 2,
    },
    # Personal relevance — fill with your unit/name to boost docs that concern you.
    # e.g. {"khoa học tự nhiên": 3, "hoàng anh đức": 5}
    "Liên quan trực tiếp": {},
}

HIGH_THRESHOLD = 8
MEDIUM_THRESHOLD = 4

LEVEL_EMOJI = {"HIGH": "🔴", "MEDIUM": "🟠", "LOW": "⚪"}

# Deadline date cues -> capture a following date/time token for display.
_DEADLINE_CUE = re.compile(
    r"(trước ngày|trước|chậm nhất(?:\s*(?:là|vào)?)?|hạn(?:\s*(?:nộp|cuối))?|"
    r"thời hạn|trước)\s*"
    r"((?:\d{1,2}h\d{0,2}\s*)?(?:ngày\s*)?\d{1,2}[/\-.]\d{1,2}(?:[/\-.]\d{2,4})?)",
    re.IGNORECASE,
)


@dataclass
class Score:
    value: int
    level: str                       # HIGH | MEDIUM | LOW
    reasons: list[str] = field(default_factory=list)
    deadline_hint: str = ""

    @property
    def emoji(self) -> str:
        return LEVEL_EMOJI.get(self.level, "⚪")

    def meets(self, min_level: str) -> bool:
        order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        return order[self.level] >= order[min_level.upper()]


def _level(value: int) -> str:
    if value >= HIGH_THRESHOLD:
        return "HIGH"
    if value >= MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def score_text(text: str, party: str = "") -> Score:
    """Score arbitrary text (subject) plus an optional party/sender string."""
    haystack = f"{text} {party}".lower()
    total = 0
    reasons: list[str] = []
    for category, phrases in RULES.items():
        best_phrase, best_weight = None, 0
        for phrase, weight in phrases.items():
            if phrase in haystack and weight > best_weight:
                best_phrase, best_weight = phrase, weight
        if best_phrase:
            total += best_weight
            reasons.append(f"{category}: “{best_phrase}” (+{best_weight})")

    deadline_hint = ""
    m = _DEADLINE_CUE.search(text)
    if m:
        deadline_hint = re.sub(r"\s+", " ", m.group(0)).strip()

    return Score(value=total, level=_level(total), reasons=reasons,
                 deadline_hint=deadline_hint)


def score_document(doc: Document) -> Score:
    return score_text(doc.subject, doc.party)
