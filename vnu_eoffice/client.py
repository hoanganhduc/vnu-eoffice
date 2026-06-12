"""HTTP client for the VNU SELAB NetOffice document system.

Authenticates with the local "Office account" form (username/password -> PHPSESSID)
and talks to the per-module ExtJS JSON endpoints. All traffic stays between this
machine and eoffice.vnu.edu.vn; no third party is involved.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from . import config
from .models import Document


def _loads_lenient(text: str):
    """Parse SELAB's not-quite-JSON.

    The list endpoint returns a UTF-8 BOM and an object whose top-level keys
    ``total`` and ``results`` are unquoted: ``{ total : 5 , results : [ ... ] }``.
    The records inside ``results`` are valid JSON, so we extract ``total`` with a
    regex and parse the ``[...]`` array directly instead of mangling string values.
    """
    text = text.lstrip("﻿").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"total\s*:\s*(\d+)", text)
        total = int(m.group(1)) if m else None
        a, b = text.find("["), text.rfind("]")
        results = json.loads(text[a:b + 1]) if a != -1 and b > a else []
        return {"total": total, "results": results}


class VnuLoginError(RuntimeError):
    pass


class VnuClient:
    def __init__(self, base_url: str = config.BASE_URL):
        self.base = base_url.rstrip("/") + "/"
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": config.USER_AGENT})
        self._logged_in = False

    # -- auth ----------------------------------------------------------------
    def login(self, username: str | None = None, password: str | None = None) -> "VnuClient":
        if username is None or password is None:
            username, password = config.get_credentials()
        r0 = self.session.get(self.base + "login/", timeout=config.REQUEST_TIMEOUT)
        tok = BeautifulSoup(r0.text, "html.parser").find("input", {"name": "_token"})
        if not tok or not tok.get("value"):
            raise VnuLoginError("Could not find CSRF _token on the login page.")
        r = self.session.post(
            self.base + "login/login.php",
            data={
                "MachineID": "",
                "_token": tok["value"],
                "signInControl$UserName": username,
                "signInControl$password": password,
            },
            timeout=config.REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        # Success lands on the app frameset (includes/main.php); failure returns
        # to the login form with an error marker.
        if "Sai tên đăng nhập" in r.text or 'name="signInControl$password"' in r.text:
            raise VnuLoginError("Login failed — check VNU_EOFFICE_USERNAME / VNU_EOFFICE_PASSWORD.")
        if "includes/main.php" not in r.text and "mainframe" not in r.text:
            # Be lenient: some deployments redirect straight into a module.
            if "PHPSESSID" not in self.session.cookies:
                raise VnuLoginError("Login did not establish a session.")
        self._logged_in = True
        return self

    def whoami(self) -> str:
        """Best-effort display name of the logged-in user (from the top bar)."""
        r = self.session.get(self.base + "includes/top.php", timeout=config.REQUEST_TIMEOUT)
        soup = BeautifulSoup(r.text, "html.parser")
        for a in soup.find_all("a"):
            attrs = f"{a.get('href', '')} {a.get('onclick', '')}"
            if "PersonalSettings(1)" in attrs and a.get_text(strip=True):
                return a.get_text(strip=True)
        return ""

    def _module(self, module: str) -> dict:
        if module not in config.MODULES:
            raise ValueError(f"Unknown module {module!r}; expected one of {list(config.MODULES)}")
        return config.MODULES[module]

    def _url(self, module: str, endpoint: str) -> str:
        return f"{self.base}{self._module(module)['path']}/server/{endpoint}"

    # -- documents -----------------------------------------------------------
    def list_documents(self, module: str, page: int = 1, limit: int = 20,
                        search: str = "", unread_only: bool = False,
                        has_attach: bool = False, **extra) -> tuple[int, list[Document]]:
        """Return (total_count, [Document]) for one page of a module's list."""
        params = {
            "page": page, "start": (page - 1) * limit, "limit": limit,
            "trichyeu": search, "kieuvb": -1, "loaivanban": 0, "sovanban": 0,
            "trangthaivb": -2 if unread_only else -1, "trangthai": -1, "intid": 0,
            "favorite": 0, "attach": 1 if has_attach else 0, "butphe": 0,
            "vbtheongay": "", "xemtatca": 0,
        }
        params.update(extra)
        r = self.session.get(self._url(module, "listvb.php"), params=params,
                             timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        data = _loads_lenient(r.text)
        docs = [Document.from_record(module, rec) for rec in data.get("results", [])]
        return data.get("total") or len(docs), docs

    def recent(self, module: str, limit: int = 60, **kw) -> list[Document]:
        """Most recent documents (first page) of a module."""
        _, docs = self.list_documents(module, page=1, limit=limit, **kw)
        return docs

    def attachments(self, module: str, intid: str) -> list[dict]:
        """List a document's attachment files: [{name, size, date, itemId}, ...]."""
        r = self.session.post(self._url(module, "attach.list.php"),
                             data={"id": intid}, timeout=config.REQUEST_TIMEOUT)
        r.raise_for_status()
        try:
            return _loads_lenient(r.text) or []
        except (json.JSONDecodeError, ValueError):
            return []

    def detail_text(self, module: str, intid: str) -> str:
        """Fetch the document detail (viewvb.php) and return its visible text."""
        r = self.session.post(self._url(module, "viewvb.php"),
                             data={"id": intid}, timeout=config.REQUEST_TIMEOUT)
        if r.status_code != 200:
            return ""
        return BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)

    def download_file(self, module: str, item_id: str, dest: Path) -> Path:
        """Download a single attachment by its file itemId to dest."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self.session.get(self._url(module, f"download.php?intid={item_id}"),
                              stream=True, timeout=config.REQUEST_TIMEOUT) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(chunk_size=65536):
                    if chunk:
                        fh.write(chunk)
        return dest

    def download_all(self, doc: Document, dest_dir: Path | None = None) -> list[Path]:
        """Download every attachment of a Document; returns the saved file paths."""
        config.ensure_dirs()
        dest_dir = Path(dest_dir) if dest_dir else (
            config.DOCS_DIR / doc.module / f"{doc.number or '0'}_{doc.intid}")
        saved: list[Path] = []
        for i, f in enumerate(self.attachments(doc.module, doc.intid)):
            name = _safe_name(f.get("name") or f"attachment_{i}")
            item_id = f.get("itemId") or f.get("intid")
            if not item_id:
                continue
            saved.append(self.download_file(doc.module, str(item_id), dest_dir / name))
        return saved


_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_name(name: str) -> str:
    name = _UNSAFE.sub("_", str(name)).strip().strip(".")
    return name or "file"
