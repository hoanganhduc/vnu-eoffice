"""Configuration, paths, and credential loading for vnu_eoffice.

Nothing secret is hard-coded. Credentials and the Telegram bot token are read
from a JSON secrets file (default ~/.config/vnu-eoffice/secrets.json) or environment
variables, so they never live in the codebase or the repository.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# --- Site -------------------------------------------------------------------
BASE_URL = os.environ.get("VNU_BASE_URL", "https://eoffice.vnu.edu.vn/qlvb/")
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
REQUEST_TIMEOUT = int(os.environ.get("VNU_TIMEOUT", "30"))

# --- Module definitions -----------------------------------------------------
# Each e-office module is a separate ExtJS sub-app under the same login session.
# field maps normalise the two modules' differing record shapes into Document.
MODULES: dict[str, dict] = {
    "den": {  # Văn bản đến — incoming
        "label": "Văn bản đến",
        "path": "office/receive",
        "number_field": "intSoden",          # số đến
        "number_label": "Số đến",
        "date_field": "strNgayden",           # ngày đến
        "date_label": "Ngày đến",
        "party_field": "strCoquanphathanh",   # cơ quan ban hành
        "party_label": "Nơi gửi",
        "signer_field": "strNguoiky",
    },
    "di": {  # Văn bản đi — outgoing
        "label": "Văn bản đi",
        "path": "office/dispatch",
        "number_field": "intSophathanh",      # số phát hành
        "number_label": "Số đi",
        "date_field": "strNgayky",            # ngày ký
        "date_label": "Ngày ký",
        "party_field": "strNoinhan",          # nơi nhận
        "party_label": "Nơi nhận",
        "signer_field": "strNguoiky",         # người ký
    },
}
DEFAULT_MODULES = ("den", "di")

# --- Data / state directories ----------------------------------------------
DATA_DIR = Path(os.environ.get(
    "VNU_DATA_DIR", str(Path.home() / ".local" / "share" / "vnu_eoffice")))
STATE_DIR = DATA_DIR / "state"
DOCS_DIR = Path(os.environ.get("VNU_DOCS_DIR", str(DATA_DIR / "documents")))
SEEN_FILE = STATE_DIR / "seen.json"
TELEGRAM_STATE_FILE = STATE_DIR / "telegram.json"


def ensure_dirs() -> None:
    for d in (DATA_DIR, STATE_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)


# --- Secrets ----------------------------------------------------------------
SECRETS_FILE = Path(os.environ.get(
    "VNU_SECRETS_FILE", str(Path.home() / "." / "secrets.json")))


def load_secrets() -> dict:
    try:
        return json.loads(SECRETS_FILE.read_text())
    except FileNotFoundError:
        return {}


def get_credentials() -> tuple[str, str]:
    """Return (username, password); env vars override the secrets file."""
    secrets = load_secrets()
    user = os.environ.get("VNU_EOFFICE_USERNAME") or secrets.get("VNU_EOFFICE_USERNAME")
    pw = os.environ.get("VNU_EOFFICE_PASSWORD") or secrets.get("VNU_EOFFICE_PASSWORD")
    if not user or not pw:
        raise RuntimeError(
            "Missing VNU credentials. Set VNU_EOFFICE_USERNAME / VNU_EOFFICE_PASSWORD "
            f"in {SECRETS_FILE} or the environment.")
    return user, pw


def get_telegram_token() -> str | None:
    secrets = load_secrets()
    return os.environ.get("TELEGRAM_BOT_TOKEN") or secrets.get("TELEGRAM_BOT_TOKEN")
