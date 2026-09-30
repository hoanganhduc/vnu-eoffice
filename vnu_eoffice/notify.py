"""Compatibility stubs for the retired direct-notification interface.

VNU eOffice retrieval code is allowed to fetch only VNU data.  Delivery is a
separate host-queue capability with an explicit channel and target policy, so
this package deliberately has no token discovery or outbound sender.
"""
from __future__ import annotations

import html
from pathlib import Path


class TelegramError(RuntimeError):
    pass


class TelegramNotifier:
    """Fail-closed adapter retained for callers pinned to the old API."""

    def __init__(self, *_args, **_kwargs):
        raise TelegramError(
            "Direct notifications are disabled; use the authenticated host delivery queue."
        )

    @classmethod
    def from_config(cls) -> "TelegramNotifier":
        return cls()


def load_chat_id() -> None:
    return None


def save_chat_id(_chat_id: str | int) -> None:
    raise TelegramError(
        "Direct notifications are disabled; use the authenticated host delivery queue."
    )


def esc(value) -> str:
    """HTML-escape a value for legacy rich-text formatting."""
    return html.escape(str(value or ""))
