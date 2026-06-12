"""Command-line interface: `vnu-eoffice <command>` (or `python -m vnu_eoffice`)."""
from __future__ import annotations

import argparse
import sys

from . import config, scheduler
from .client import VnuClient
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
        total, docs = client.list_documents(
            module, limit=args.limit, unread_only=args.unread)
        print(f"\n== {config.MODULES[module]['label']} (total {total}) ==")
        for d in docs:
            sc = score_text(d.subject, d.party)
            flag = "•" if d.unread else " "
            att = "📎" if d.has_attach else "  "
            print(f" {flag}{att} {sc.emoji}{sc.value:>2} [{d.intid}] {d.date_short} "
                  f"{d.number:>5} {d.symbol[:16]:16} | {d.subject[:60]}")
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
    _, docs = client.list_documents(args.module, limit=200)
    doc = next((d for d in docs if d.intid == str(args.id)), None)
    if doc is None:
        print(f"Document {args.id} not in the latest {args.module} list; "
              "try a larger window or check the id.")
        return 1
    paths = client.download_all(doc)
    print(f"Downloaded {len(paths)} file(s):")
    for p in paths:
        print("  ", p)
    return 0


def cmd_monitor(args) -> int:
    result = run_once(
        modules=args.modules, limit=args.limit, min_level=args.min_level,
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
    sp.add_argument("--limit", type=int, default=20)
    sp.add_argument("--unread", action="store_true", help="Only unread documents")
    sp.set_defaults(func=cmd_list)

    sp = sub.add_parser("score", help="Test the importance scorer on a phrase")
    sp.add_argument("text")
    sp.set_defaults(func=cmd_score)

    sp = sub.add_parser("download", help="Download a document's attachments")
    sp.add_argument("--module", choices=list(config.MODULES), default="den")
    sp.add_argument("--id", required=True, help="Document intid")
    sp.set_defaults(func=cmd_download)

    sp = sub.add_parser("monitor", help="Run one polling pass (fetch/score/alert)")
    sp.add_argument("--once", action="store_true", help="(default) single pass")
    sp.add_argument("--modules", type=_modules, default=config.DEFAULT_MODULES)
    sp.add_argument("--limit", type=int, default=60)
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
