"""Normalised document model shared by both e-office modules."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import config


def _clean(value) -> str:
    """Collapse the CR/LF and runs of whitespace that appear in trích yếu."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


@dataclass
class Document:
    module: str                 # "den" | "di"
    intid: str
    number: str                 # số đến / số phát hành
    symbol: str                 # số, ký hiệu
    subject: str                # trích yếu (whitespace-normalised)
    date: str                   # ngày đến / ngày ký (server format "YYYY-MM-DD HH:MM:SS")
    party: str                  # nơi gửi / nơi nhận
    signer: str = ""            # người ký
    unread: bool = False
    has_attach: bool = False
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_record(cls, module: str, rec: dict) -> "Document":
        m = config.MODULES[module]
        party = _clean(rec.get(m["party_field"]))
        signer = _clean(rec.get(m.get("signer_field", "")))
        # Outgoing records often leave "nơi nhận" blank; fall back to the signer.
        if not party and signer:
            party = f"Người ký: {signer}"
        return cls(
            module=module,
            intid=str(rec.get("intid", "")),
            number=_clean(rec.get(m["number_field"])),
            symbol=_clean(rec.get("strKyhieu")),
            subject=_clean(rec.get("strTrichyeu")),
            date=_clean(rec.get(m["date_field"])),
            party=party,
            signer=signer,
            unread=str(rec.get("statusopen", "")) == "0",
            has_attach=str(rec.get("attach", "0")) not in ("0", "", "None"),
            raw=rec,
        )

    @property
    def key(self) -> str:
        """Stable cross-module dedup key."""
        return f"{self.module}:{self.intid}"

    @property
    def module_label(self) -> str:
        return config.MODULES[self.module]["label"]

    @property
    def date_short(self) -> str:
        return self.date[:10] if self.date else ""

    def web_url(self, base: str = config.BASE_URL) -> str:
        return f"{base.rstrip('/')}/{config.MODULES[self.module]['path']}/"
