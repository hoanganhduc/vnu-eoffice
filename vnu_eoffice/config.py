"""Configuration, paths, and runtime credential loading for vnu_eoffice."""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlparse

# --- Site -------------------------------------------------------------------
DEFAULT_BASE_URL = "https://eoffice.vnu.edu.vn/qlvb/"
BASE_URL = os.environ.get("VNU_BASE_URL", DEFAULT_BASE_URL)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120 Safari/537.36"
)
REQUEST_TIMEOUT = int(os.environ.get("VNU_TIMEOUT", "30"))


def validate_base_url(base_url: str) -> None:
    """Refuse accidental credential posts to a non-VNU host."""
    if os.environ.get("VNU_ALLOW_NON_VNU_BASE_URL") == "1":
        return
    parsed = urlparse(base_url)
    expected = urlparse(DEFAULT_BASE_URL)
    if parsed.scheme != "https" or parsed.hostname != expected.hostname:
        raise RuntimeError(
            "Refusing to send VNU credentials to a non-default base URL. "
            "Set VNU_ALLOW_NON_VNU_BASE_URL=1 only for trusted test systems."
        )

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
        ensure_private_dir(d)


def ensure_private_dir(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def _no_follow_flags(flags: int) -> int:
    return flags | getattr(os, "O_NOFOLLOW", 0)


def write_private_text(path: Path, text: str) -> None:
    path = Path(path)
    ensure_private_dir(path.parent)
    flags = _no_follow_flags(os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def ensure_private_file(path: Path) -> None:
    path = Path(path)
    ensure_private_dir(path.parent)
    flags = _no_follow_flags(os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    fd = os.open(path, flags, 0o600)
    os.close(fd)
    try:
        path.chmod(0o600)
    except OSError:
        pass


# --- Secrets ----------------------------------------------------------------
DEFAULT_SECRETS_FILE = Path.home() / ".config" / "vnu-eoffice" / "secrets.json"
SECRETS_FILE = Path(os.environ["VNU_SECRETS_FILE"]) if os.environ.get("VNU_SECRETS_FILE") else DEFAULT_SECRETS_FILE


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
        raise RuntimeError("Missing VNU credentials.")
    return user, pw


def get_telegram_token() -> str | None:
    secrets = load_secrets()
    return os.environ.get("TELEGRAM_BOT_TOKEN") or secrets.get("TELEGRAM_BOT_TOKEN")
