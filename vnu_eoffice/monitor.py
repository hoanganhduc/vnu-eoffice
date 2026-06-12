"""Polling orchestration: fetch -> dedup -> score -> alert -> (download) -> (delete).

Runs entirely locally. On the very first run it records a baseline of the
documents currently visible (without alerting on the whole backlog); subsequent
runs alert only on genuinely new documents that meet the importance threshold.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import config
from .client import VnuClient
from .importance import Score, score_document
from .models import Document
from .notify import TelegramNotifier, esc

SEEN_CAP = 4000  # remembered intids per module (newest kept)


# -- dedup state -------------------------------------------------------------
def load_seen() -> dict:
    try:
        return json.loads(config.SEEN_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_seen(state: dict) -> None:
    config.ensure_dirs()
    config.SEEN_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=0))


# -- result reporting --------------------------------------------------------
@dataclass
class Alert:
    doc: Document
    score: Score
    files: list[Path] = field(default_factory=list)
    deleted: bool = False


@dataclass
class RunResult:
    first_run: bool = False
    new_count: int = 0
    alerts: list[Alert] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if self.first_run:
            return f"Baseline recorded ({self.new_count} documents in view). No alerts on first run."
        return (f"{self.new_count} new document(s); "
                f"{len(self.alerts)} alert(s); {len(self.errors)} error(s).")


# -- alert formatting --------------------------------------------------------
def format_alert(doc: Document, score: Score, files: list[Path]) -> str:
    m = config.MODULES[doc.module]
    lines = [
        f"{score.emoji} <b>[{score.level}] {esc(doc.module_label)} mới</b>",
        f"<b>{esc(m['number_label'])}:</b> {esc(doc.number)}  •  {esc(doc.date_short)}",
    ]
    if doc.symbol:
        lines.append(f"<b>Ký hiệu:</b> {esc(doc.symbol)}")
    if doc.party:
        lines.append(f"<b>{esc(m['party_label'])}:</b> {esc(doc.party)}")
    lines.append(f"<b>Trích yếu:</b> {esc(doc.subject)}")
    if score.deadline_hint:
        lines.append(f"⏰ <b>Hạn:</b> {esc(score.deadline_hint)}")
    if score.reasons:
        lines.append(f"<i>Lý do (score {score.value}):</i> {esc('; '.join(score.reasons))}")
    if doc.has_attach:
        n = len(files)
        lines.append(f"📎 {n} đính kèm" + (" — đã tải về" if n else ""))
    lines.append(f'<a href="{esc(doc.web_url())}">Mở trên e-office</a>')
    return "\n".join(lines)


# -- core --------------------------------------------------------------------
def run_once(
    modules: tuple[str, ...] = config.DEFAULT_MODULES,
    limit: int = 60,
    min_level: str = "MEDIUM",
    download: bool = False,
    delete_after: bool = False,
    send_files: bool = False,
    notify: bool = True,
    dry_run: bool = False,
    client: VnuClient | None = None,
    notifier: TelegramNotifier | None = None,
) -> RunResult:
    config.ensure_dirs()
    client = client or VnuClient().login()
    seen = load_seen()
    first_run = not seen.get("_initialized")
    result = RunResult(first_run=first_run)

    if notify and notifier is None:
        try:
            notifier = TelegramNotifier.from_config()
        except Exception as e:  # missing token/chat id — degrade to no-notify
            result.errors.append(f"Telegram disabled: {e}")
            notifier = None

    for module in modules:
        try:
            docs = client.recent(module, limit=limit)
        except Exception as e:
            result.errors.append(f"[{module}] list failed: {e}")
            continue
        seen_ids = set(seen.get(module, []))
        new_docs = [d for d in docs if d.intid not in seen_ids]
        result.new_count += len(new_docs)

        if not first_run:
            for doc in new_docs:
                score = score_document(doc)
                if not score.meets(min_level):
                    continue
                try:
                    result.alerts.append(
                        _handle_alert(client, notifier, doc, score,
                                      download, delete_after, send_files, dry_run))
                except Exception as e:
                    result.errors.append(f"[{module}] alert {doc.intid} failed: {e}")

        # Update remembered ids (page is newest-first; keep newest SEEN_CAP).
        merged, ordered = set(), []
        for cid in [d.intid for d in docs] + seen.get(module, []):
            if cid not in merged:
                merged.add(cid)
                ordered.append(cid)
        seen[module] = ordered[:SEEN_CAP]

    seen["_initialized"] = True
    if not dry_run:
        save_seen(seen)

    if first_run and notifier and not dry_run:
        try:
            notifier.send_message(
                f"✅ <b>VNU e-office monitor đã bắt đầu.</b>\n"
                f"Đang theo dõi: {esc(', '.join(config.MODULES[m]['label'] for m in modules))}.\n"
                f"Sẽ thông báo văn bản mới quan trọng (mức ≥ {esc(min_level)}).")
        except Exception as e:
            result.errors.append(f"baseline notify failed: {e}")

    return result


def _handle_alert(client, notifier, doc, score, download, delete_after,
                  send_files, dry_run) -> Alert:
    files: list[Path] = []
    if download and doc.has_attach and not dry_run:
        files = client.download_all(doc)

    if notifier and not dry_run:
        notifier.send_message(format_alert(doc, score, files))
        if send_files:
            for f in files:
                notifier.send_document(f, caption=f"{doc.symbol} — {doc.subject[:120]}")

    alert = Alert(doc=doc, score=score, files=files)
    # "Delete after checking and sending": wipe the local copy once alerted.
    if delete_after and files and not dry_run:
        _delete_files(files)
        alert.deleted = True
        alert.files = []
    return alert


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
