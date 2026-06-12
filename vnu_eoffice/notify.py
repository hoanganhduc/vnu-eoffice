"""Telegram alerting. The only outbound channel; sends alert text (and, if you
explicitly opt in, the document file) to the Telegram Bot API."""
from __future__ import annotations

import html
import json
import os
from pathlib import Path

import requests

from . import config

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramError(RuntimeError):
    pass


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str | int | None = None):
        self.token = token
        self.chat_id = str(chat_id) if chat_id is not None else None

    # -- construction --------------------------------------------------------
    @classmethod
    def from_config(cls) -> "TelegramNotifier":
        token = config.get_telegram_token()
        if not token:
            raise RuntimeError("Telegram bot token is not configured.")
        return cls(token, chat_id=load_chat_id())

    def _call(self, method: str, **kwargs) -> dict:
        r = requests.post(API.format(token=self.token, method=method),
                          timeout=config.REQUEST_TIMEOUT, **kwargs)
        try:
            r.raise_for_status()
            data = r.json()
        except requests.RequestException as e:
            raise TelegramError(f"Telegram {method} request failed: {e}") from e
        except ValueError as e:
            raise TelegramError(f"Telegram {method} returned non-JSON response.") from e
        if not data.get("ok"):
            desc = data.get("description") or data
            raise TelegramError(f"Telegram {method} failed: {desc}")
        return data

    # -- chat-id discovery ---------------------------------------------------
    def get_me(self) -> dict:
        return self._call("getMe")

    def discover_chat_ids(self) -> list[dict]:
        """Return chats that have messaged the bot: [{id, type, name}, ...]."""
        data = self._call("getUpdates")
        out, seen = [], set()
        for u in data.get("result", []):
            msg = (u.get("message") or u.get("edited_message")
                   or u.get("channel_post") or {})
            ch = msg.get("chat") or {}
            cid = ch.get("id")
            if cid is None or cid in seen:
                continue
            seen.add(cid)
            name = (ch.get("title") or ch.get("username")
                    or f"{ch.get('first_name', '')} {ch.get('last_name', '')}".strip())
            out.append({"id": cid, "type": ch.get("type"), "name": name})
        return out

    # -- sending -------------------------------------------------------------
    def send_message(self, text: str, parse_mode: str = "HTML",
                     disable_preview: bool = True) -> dict:
        if not self.chat_id:
            raise RuntimeError("Telegram chat id is not configured.")
        return self._call("sendMessage", data={
            "chat_id": self.chat_id, "text": text, "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        })

    def send_document(self, path: Path, caption: str = "") -> dict:
        if not self.chat_id:
            raise RuntimeError("Telegram chat id is not configured.")
        path = Path(path)
        with open(path, "rb") as fh:
            return self._call("sendDocument",
                              data={"chat_id": self.chat_id, "caption": caption[:1024]},
                              files={"document": (path.name, fh)})


# -- chat-id persistence -----------------------------------------------------
def load_chat_id() -> str | None:
    if os.environ.get("TELEGRAM_CHAT_ID"):
        return os.environ["TELEGRAM_CHAT_ID"]
    secrets = config.load_secrets()
    if secrets.get("TELEGRAM_CHAT_ID"):
        return str(secrets["TELEGRAM_CHAT_ID"])
    try:
        return str(json.loads(config.TELEGRAM_STATE_FILE.read_text())["chat_id"])
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return None


def save_chat_id(chat_id: str | int) -> None:
    config.ensure_dirs()
    config.write_private_text(config.TELEGRAM_STATE_FILE,
                              json.dumps({"chat_id": str(chat_id)}))


def esc(value) -> str:
    """HTML-escape a value for Telegram HTML parse mode."""
    return html.escape(str(value or ""))
