"""Polling orchestration: fetch -> dedup -> alert -> (download) -> (delete).

Runs entirely locally. On the very first run it records a baseline of the
documents currently visible (without alerting on the whole backlog); subsequent
runs alert on every genuinely new document.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .client import VnuClient
from .documents import fetch_documents
from .models import Document
from .notify import TelegramNotifier, esc

SEEN_CAP = 4000  # remembered intids per module (newest kept)
HASHED_SEEN_PREFIX = "hmac-sha256:"


# -- dedup state -------------------------------------------------------------
def load_seen() -> dict:
    try:
        return json.loads(config.SEEN_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(state: dict) -> None:
    config.ensure_dirs()
    config.write_private_text(config.SEEN_FILE,
                              json.dumps(state, ensure_ascii=False, indent=0))


def seen_state_id(intid: str) -> str:
    value = str(intid)
    if not config.hash_seen_ids_enabled():
        return value
    key = config.get_seen_hmac_key()
    if not key:
        raise RuntimeError("Missing HMAC key for hashed seen-state ids.")
    digest = hmac.new(str(key).encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
    return HASHED_SEEN_PREFIX + digest


def initialized_modules(state: dict) -> set[str]:
    mods = set(state.get("_initialized_modules", []))
    # Backward compatibility for state written by versions that used one global
    # flag. Only modules with remembered ids count as initialized.
    if state.get("_initialized"):
        mods.update(m for m in config.MODULES if state.get(m))
    return mods


def remember_module_initialized(state: dict, module: str) -> None:
    mods = initialized_modules(state)
    mods.add(module)
    state["_initialized_modules"] = sorted(mods)
    state["_initialized"] = bool(mods)


# -- result reporting --------------------------------------------------------
@dataclass
class Alert:
    doc: Document
    files: list[Path] = field(default_factory=list)
    deleted: bool = False


@dataclass
class RunResult:
    first_run: bool = False
    baseline_modules: list[str] = field(default_factory=list)
    baseline_count: int = 0
    new_count: int = 0
    alerts: list[Alert] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.first_run and self.baseline_modules:
            return (f"Baseline recorded ({self.baseline_count} documents in view; "
                    f"modules: {', '.join(self.baseline_modules)}). No alerts on first run.")
        parts = [
            f"{self.new_count} new document(s)",
            f"{len(self.alerts)} alert(s)",
            f"{len(self.errors)} error(s)",
        ]
        if self.baseline_modules:
            parts.append(f"baselined modules: {', '.join(self.baseline_modules)}")
        return "; ".join(parts) + "."


# -- alert formatting --------------------------------------------------------
def format_alert(doc: Document, files: list[Path]) -> str:
    m = config.MODULES[doc.module]
    lines = [
        f"📄 <b>{esc(doc.module_label)} mới</b>",
        f"<b>{esc(m['number_label'])}:</b> {esc(doc.number)}  •  {esc(doc.date_short)}",
    ]
    if doc.symbol:
        lines.append(f"<b>Ký hiệu:</b> {esc(doc.symbol)}")
    if doc.party:
        lines.append(f"<b>{esc(m['party_label'])}:</b> {esc(doc.party)}")
    lines.append(f"<b>Trích yếu:</b> {esc(doc.subject)}")
    if doc.has_attach:
        n = len(files)
        lines.append(f"📎 {n} đính kèm" + (" — đã tải về" if n else ""))
    lines.append(f'<a href="{esc(doc.web_url())}">Mở trên e-office</a>')
    return "\n".join(lines)


# -- core --------------------------------------------------------------------
def run_once(
    modules: tuple[str, ...] = config.DEFAULT_MODULES,
    limit: int = 60,
    pages: int = config.DEFAULT_FETCH_PAGES,
    download: bool = False,
    delete_after: bool = False,
    send_files: bool = False,
    notify: bool = True,
    dry_run: bool = False,
    client: VnuClient | None = None,
    notifier: TelegramNotifier | None = None,
) -> RunResult:
    if not modules:
        raise ValueError("At least one module must be selected.")
    config.ensure_dirs()
    client = client or VnuClient().login()
    seen = load_seen()
    initialized = initialized_modules(seen)
    first_run = not initialized
    result = RunResult(first_run=first_run)

    if notify and notifier is None:
        try:
            notifier = TelegramNotifier.from_config()
        except Exception as e:  # missing token/chat id — degrade to no-notify
            result.errors.append(f"Telegram disabled: {e}")
            notifier = None

    for module in modules:
        try:
            _, docs = fetch_documents(client, module, limit=limit, pages=pages)
        except Exception as e:
            result.errors.append(f"[{module}] list failed: {e}")
            continue
        doc_state_ids = {d.intid: seen_state_id(d.intid) for d in docs}
        seen_ids = set(seen.get(module, []))
        new_docs = [d for d in docs if doc_state_ids[d.intid] not in seen_ids]
        result.new_count += len(new_docs)

        if module not in initialized:
            result.baseline_modules.append(module)
            result.baseline_count += len(docs)
            seen[module] = _merge_seen([doc_state_ids[d.intid] for d in docs], seen.get(module, []))
            remember_module_initialized(seen, module)
            continue

        failed_ids: set[str] = set()
        if module in initialized:
            for doc in new_docs:
                try:
                    result.alerts.append(
                        _handle_alert(
                            client,
                            notifier,
                            doc,
                            download,
                            delete_after,
                            send_files,
                            dry_run,
                            require_delivery=notify,
                        )
                    )
                except Exception as e:
                    failed_ids.add(doc_state_ids[doc.intid])
                    result.errors.append(f"[{module}] alert delivery failed: {e}")

        # Update remembered ids (page is newest-first; keep newest SEEN_CAP).
        ids_to_remember = [doc_state_ids[d.intid] for d in docs if doc_state_ids[d.intid] not in failed_ids]
        seen[module] = _merge_seen(ids_to_remember, seen.get(module, []))

    if not dry_run:
        save_seen(seen)

    if first_run and notifier and not dry_run:
        try:
            notifier.send_message(
                f"✅ <b>VNU e-office monitor đã bắt đầu.</b>\n"
                f"Đang theo dõi: {esc(', '.join(config.MODULES[m]['label'] for m in modules))}.\n"
                "Sẽ thông báo tất cả văn bản mới.")
        except Exception as e:
            result.errors.append(f"baseline notify failed: {e}")

    return result


def _handle_alert(client, notifier, doc, download, delete_after,
                  send_files, dry_run, require_delivery=True) -> Alert:
    files: list[Path] = []
    alert = Alert(doc=doc, files=files)
    try:
        if download and doc.has_attach and not dry_run:
            files = client.download_all(doc)
            alert.files = files

        if require_delivery and notifier is None and not dry_run:
            raise RuntimeError("Telegram notifier is unavailable.")

        if notifier and not dry_run:
            notifier.send_message(format_alert(doc, files))
            if send_files:
                for f in files:
                    notifier.send_document(f, caption=f"{doc.symbol} — {doc.subject[:120]}")
        return alert
    finally:
        # If the user asked us not to retain downloaded copies, honor that even
        # when delivery fails. The next retry can download again if needed.
        if delete_after and files and not dry_run:
            _delete_files(files)
            alert.deleted = True
            alert.files = []


def _delete_files(files: list[Path]) -> None:
    dirs = set()
    for f in files:
        try:
            Path(f).unlink(missing_ok=True)
            dirs.add(Path(f).parent)
        except OSError:
            pass
    for d in dirs:  # remove now-empty per-document folders
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
        except OSError:
            pass


def _merge_seen(newest_ids: list[str], old_ids: list[str]) -> list[str]:
    merged, ordered = set(), []
    for cid in newest_ids + old_ids:
        if cid not in merged:
            merged.add(cid)
            ordered.append(cid)
    return ordered[:SEEN_CAP]
