"""Command-line interface: `vnu-eoffice <command>` (or `python -m vnu_eoffice`)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, scheduler
from .client import VnuClient
from .documents import (
    download_documents,
    fetch_documents,
    parse_document_refs,
    search_documents,
    send_documents,
)
from .importance import score_text
from .monitor import run_once
from .notify import TelegramNotifier, save_chat_id


def _modules(arg: str) -> tuple[str, ...]:
    mods = tuple(m.strip() for m in arg.split(",") if m.strip())
    if not mods:
        raise argparse.ArgumentTypeError("at least one module is required")
    bad = [m for m in mods if m not in config.MODULES]
    if bad:
        raise argparse.ArgumentTypeError(f"unknown module(s): {bad}; choose from {list(config.MODULES)}")
    return mods


def _schedule_interval(arg: str) -> int:
    try:
        value = int(arg)
    except ValueError as e:
        raise argparse.ArgumentTypeError("--every must be an integer") from e
    try:
        return scheduler.validate_interval(value)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


def _document_refs(ids: list[str], default_module: str):
    try:
        return parse_document_refs(ids, default_module=default_module)
    except ValueError as e:
        raise argparse.ArgumentTypeError(str(e)) from e


# -- commands ----------------------------------------------------------------
def cmd_test_login(args) -> int:
    client = VnuClient().login()
    name = client.whoami() or "(unknown)"
    print(f"Login OK. Logged in as: {name}")
    for m in config.DEFAULT_MODULES:
        total, _ = client.list_documents(m, limit=1)
        print(f"  {config.MODULES[m]['label']}: {total} documents")
    return 0


def cmd_setup_telegram(args) -> int:
    notifier = TelegramNotifier.from_config()
    me = notifier.get_me()
    if not me.get("ok"):
        print("Bot token invalid or unreachable:", me)
        return 1
    bot = me["result"].get("username")
    print(f"Bot: @{bot}")
    chats = notifier.discover_chat_ids()
    if not chats:
        print(f"\nNo chats found. Open Telegram, message @{bot} (send anything, e.g. /start),")
        print("then run `vnu-eoffice setup-telegram` again.")
        return 1
    if args.chat_id:
        save_chat_id(args.chat_id)
        print(f"Saved chat_id = {args.chat_id}")
        return 0
    if len(chats) == 1:
        save_chat_id(chats[0]["id"])
        print(f"Saved chat_id = {chats[0]['id']} ({chats[0]['name']})")
        return 0
    print("Multiple chats found — re-run with --chat-id <id>:")
    for c in chats:
        print(f"  {c['id']}  {c['type']}  {c['name']}")
    return 1


def cmd_list(args) -> int:
    client = VnuClient().login()
    for module in args.modules:
        total, docs = fetch_documents(module=module, client=client,
                                      limit=args.limit, pages=args.pages)
        print(f"\n== {config.MODULES[module]['label']} (total {total}) ==")
        for d in docs:
            sc = score_text(d.subject, d.party)
            att = "📎" if d.has_attach else "  "
            print(f" {att} {sc.emoji}{sc.value:>2} [{d.intid}] {d.date_short} "
                  f"{d.number:>5} {d.symbol[:16]:16} | {d.subject[:60]}")
    return 0


def cmd_search(args) -> int:
    client = VnuClient().login()
    query = " ".join(args.keywords)
    docs = search_documents(
        client,
        query,
        modules=args.modules,
        limit=args.limit,
        pages=args.pages,
        unread_only=False,
        has_attach=args.has_attach,
    )
    if not docs:
        print("No matching documents.")
        return 0
    for d in docs:
        sc = score_text(d.subject, d.party)
        att = "📎" if d.has_attach else "  "
        print(f"{d.module}:{d.intid} {att} {sc.emoji}{sc.value:>2} "
              f"{d.date_short} {d.number:>5} {d.symbol[:16]:16} | {d.subject[:80]}")
    return 0


def cmd_score(args) -> int:
    sc = score_text(args.text)
    print(f"score={sc.value} level={sc.level}")
    for r in sc.reasons:
        print("  -", r)
    if sc.deadline_hint:
        print("  deadline:", sc.deadline_hint)
    return 0


def cmd_download(args) -> int:
    client = VnuClient().login()
    refs = _document_refs(args.ids, args.module)
    items = download_documents(
        client,
        refs,
        dest_dir=Path(args.dest_dir) if args.dest_dir else None,
        lookup_limit=args.lookup_limit,
    )
    total = sum(len(item.files) for item in items)
    print(f"Downloaded {total} file(s) from {len(items)} document(s):")
    for item in items:
        print(f"  {item.doc.module}:{item.doc.intid} {item.doc.symbol} | {item.doc.subject[:80]}")
        for path in item.files:
            print("    ", path)
    return 0


def cmd_send(args) -> int:
    client = VnuClient().login()
    notifier = TelegramNotifier.from_config()
    refs = _document_refs(args.ids, args.module)
    items = send_documents(
        client,
        notifier,
        refs,
        delete_after=args.delete_after,
        dest_dir=Path(args.dest_dir) if args.dest_dir else None,
        lookup_limit=args.lookup_limit,
    )
    total = sum(len(item.files) for item in items)
    print(f"Sent {len(items)} document(s), {total} attachment file(s).")
    if args.delete_after:
        print("Deleted local downloaded files after sending.")
    return 0


def cmd_monitor(args) -> int:
    result = run_once(
        modules=args.modules, limit=args.limit, min_level=args.min_level,
        pages=args.pages,
        download=args.download, delete_after=args.delete_after,
        send_files=args.send_files, notify=not args.no_notify, dry_run=args.dry_run,
    )
    print(result.summary())
    if not args.quiet:
        for a in result.alerts:
            print(f"  {a.score.emoji} [{a.doc.module}] {a.doc.symbol} — {a.doc.subject[:70]}"
                  + ("  (files deleted)" if a.deleted else ""))
    for e in result.errors:
        print("  ! ", e)
    return 1 if result.errors else 0


def cmd_schedule(args) -> int:
    margs = (f"monitor --once --modules {','.join(args.modules)} --min-level {args.min_level}"
             + f" --pages {args.pages}"
             + (" --download" if args.download else "")
             + (" --delete-after" if args.delete_after else "")
             + " --quiet")
    if args.remove:
        print("Removed." if scheduler.remove() else "No existing entry.")
        return 0
    if args.preview:
        print(scheduler.preview(args.every, margs))
        return 0
    line = scheduler.install(args.every, margs)
    print(f"Installed schedule (every {args.every} min):\n  {line}")
    print(f"Logs: {scheduler.log_path()}")
    return 0


# -- parser ------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vnu-eoffice",
                                description="Retrieve, score, and alert on VNU e-office documents (local-only).")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("test-login", help="Verify credentials and show document counts").set_defaults(func=cmd_test_login)

    sp = sub.add_parser("setup-telegram", help="Discover and save the Telegram chat id")
    sp.add_argument("--chat-id", help="Use this chat id directly")
    sp.set_defaults(func=cmd_setup_telegram)

    sp = sub.add_parser("list", help="List recent documents with importance scores")
    sp.add_argument("--modules", type=_modules, default=config.DEFAULT_MODULES)
    sp.add_argument("--limit", type=int, default=20, help="Documents per page")
    sp.add_argument("--pages", type=int, default=config.DEFAULT_FETCH_PAGES,
                    help=f"Pages to fetch per module (default {config.DEFAULT_FETCH_PAGES})")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("search", help="Search documents by subject keywords")
    sp.add_argument("keywords", nargs="+")
    sp.add_argument("--modules", type=_modules, default=config.DEFAULT_MODULES)
    sp.add_argument("--limit", type=int, default=20, help="Documents per page")
    sp.add_argument("--pages", type=int, default=config.DEFAULT_FETCH_PAGES,
                    help=f"Pages to fetch per module (default {config.DEFAULT_FETCH_PAGES})")
    sp.add_argument("--has-attach", action="store_true", help="Only documents with attachments")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("score", help="Test the importance scorer on a phrase")
    sp.add_argument("text")
    sp.set_defaults(func=cmd_score)

    sp = sub.add_parser("download", help="Download document attachment(s)")
    sp.add_argument("--module", choices=list(config.MODULES), default="den")
    sp.add_argument("--id", dest="ids", required=True, action="append",
                    help="Document intid; repeatable. Accepts module:id.")
    sp.add_argument("--dest-dir", help="Download root directory")
    sp.add_argument("--lookup-limit", type=int, default=200,
                    help="Fallback recent-document lookup window")
    sp.set_defaults(func=cmd_download)

    sp = sub.add_parser("send", help="Download and send document attachment(s) via Telegram")
    sp.add_argument("--module", choices=list(config.MODULES), default="den")
    sp.add_argument("--id", dest="ids", required=True, action="append",
                    help="Document intid; repeatable. Accepts module:id.")
    sp.add_argument("--dest-dir", help="Download root directory")
    sp.add_argument("--lookup-limit", type=int, default=200,
                    help="Fallback recent-document lookup window")
    sp.add_argument("--delete-after", action="store_true",
                    help="Delete local downloaded files after sending")
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("monitor", help="Run one polling pass (fetch/score/alert)")
    sp.add_argument("--once", action="store_true", help="(default) single pass")
    sp.add_argument("--modules", type=_modules, default=config.DEFAULT_MODULES)
    sp.add_argument("--limit", type=int, default=60, help="Documents per page")
    sp.add_argument("--pages", type=int, default=config.DEFAULT_FETCH_PAGES,
                    help=f"Pages to fetch per module (default {config.DEFAULT_FETCH_PAGES})")
    sp.add_argument("--min-level", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM")
    sp.add_argument("--download", action="store_true", help="Download attachments of alerted docs")
    sp.add_argument("--delete-after", action="store_true",
                    help="Delete downloaded files after checking and sending")
    sp.add_argument("--send-files", action="store_true",
                    help="Also send the document files via Telegram (sends content off-machine)")
    sp.add_argument("--no-notify", action="store_true", help="Do not send Telegram messages")
    sp.add_argument("--dry-run", action="store_true", help="No downloads, sends, or state writes")
    sp.add_argument("--quiet", action="store_true", help="Suppress alert subject lines in output")
    sp.set_defaults(func=cmd_monitor)

    sp = sub.add_parser("schedule", help="Install a recurring scheduled monitor (cron / Task Scheduler)")
    sp.add_argument("--every", type=_schedule_interval, default=15, help="Minutes between runs (default 15)")
    sp.add_argument("--modules", type=_modules, default=config.DEFAULT_MODULES)
    sp.add_argument("--pages", type=int, default=config.DEFAULT_FETCH_PAGES,
                    help=f"Pages to fetch per module (default {config.DEFAULT_FETCH_PAGES})")
    sp.add_argument("--min-level", choices=["LOW", "MEDIUM", "HIGH"], default="MEDIUM")
    sp.add_argument("--download", action="store_true")
    sp.add_argument("--delete-after", action="store_true")
    sp.add_argument("--preview", action="store_true", help="Print the schedule line without installing")
    sp.add_argument("--remove", action="store_true", help="Remove the installed schedule")
    sp.set_defaults(func=cmd_schedule)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
