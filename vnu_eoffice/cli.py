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
    search_documents,
    send_documents,
)
from .items import (
    format_download_summary,
    format_listing,
    format_mapping_listing,
    format_monitor_result,
    load_mapping,
    resolve_document_refs,
    save_mapping,
    split_text,
)
from .monitor import delete_files, run_once, save_seen
from .notify import TelegramNotifier, esc, save_chat_id


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
    docs = []
    for module in args.modules:
        _, module_docs = fetch_documents(
            module=module,
            client=client,
            limit=args.limit,
            pages=args.pages,
        )
        docs.extend(module_docs)
    save_mapping("latest", docs, modules=args.modules)
    print(format_listing(
        "VNU eOffice latest documents",
        f"Latest documents - scanned {args.pages} page(s).",
        docs,
        args.modules,
    ))
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
    save_mapping("search", docs, query=query, modules=args.modules)
    if not docs:
        print(format_listing(
            "VNU eOffice document search",
            f"Search: {query}\nScanned {args.pages} page(s).",
            docs,
            args.modules,
        ))
        return 0
    print(format_listing(
        "VNU eOffice document search",
        f"Search: {query}\nScanned {args.pages} page(s).",
        docs,
        args.modules,
    ))
    return 0


def cmd_items(args) -> int:
    print(format_mapping_listing(load_mapping(args.source)))
    return 0


def cmd_download(args) -> int:
    refs = resolve_document_refs(
        ids=args.ids,
        items=args.items,
        all_items=args.all,
        source=args.source,
        default_module=args.module,
    )
    client = VnuClient().login()
    items = download_documents(
        client,
        refs,
        dest_dir=Path(args.dest_dir) if args.dest_dir else None,
        lookup_limit=args.lookup_limit,
    )
    print(format_download_summary(items, sent=False, deleted=False))
    for item in items:
        for path in item.files:
            print("  ", path)
    return 0


def cmd_send(args) -> int:
    refs = resolve_document_refs(
        ids=args.ids,
        items=args.items,
        all_items=args.all,
        source=args.source,
        default_module=args.module,
    )
    client = VnuClient().login()
    notifier = TelegramNotifier.from_config()
    items = send_documents(
        client,
        notifier,
        refs,
        delete_after=args.delete_after,
        dest_dir=Path(args.dest_dir) if args.dest_dir else None,
        lookup_limit=args.lookup_limit,
    )
    print(format_download_summary(items, sent=True, deleted=args.delete_after))
    return 0


def cmd_monitor(args) -> int:
    should_notify = not args.no_notify and not args.dry_run
    result = run_once(
        modules=args.modules, limit=args.limit,
        pages=args.pages,
        download=args.download or args.send_files,
        delete_after=False,
        send_files=False,
        notify=False,
        dry_run=args.dry_run,
        notify_alerts=False,
        save_seen_state=False,
    )
    text = format_monitor_result(result, args.modules)
    if args.quiet:
        print(result.summary())
    else:
        print(text)

    alert_docs = [alert.doc for alert in result.alerts]
    delivery_error = None
    should_send_summary = should_notify and (alert_docs or (result.first_run and result.baseline_modules))
    if should_send_summary:
        try:
            notifier = TelegramNotifier.from_config()
            send_plain_text(notifier, text)
            if args.send_files:
                for alert in result.alerts:
                    for path in alert.files:
                        notifier.send_document(path, caption=f"{alert.doc.symbol} - {alert.doc.subject[:120]}")
        except Exception as e:
            delivery_error = f"summary delivery failed: {e}"
            result.errors.append(delivery_error)

    if args.delete_after:
        delete_files(path for alert in result.alerts for path in alert.files)

    if not args.dry_run and delivery_error is None:
        save_seen(result.seen_state)
        if alert_docs:
            save_mapping("monitor", alert_docs, query="new monitor alerts", modules=args.modules)

    for e in result.errors:
        print("  ! ", e)
    return 1 if result.errors else 0


def send_plain_text(notifier: TelegramNotifier, text: str) -> None:
    for chunk in split_text(text, 3800):
        notifier.send_message(esc(chunk))


def cmd_schedule(args) -> int:
    margs = (f"monitor --once --modules {','.join(args.modules)}"
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
                                description="Retrieve and alert on VNU e-office documents (local-only).")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("test-login", help="Verify credentials and show document counts").set_defaults(func=cmd_test_login)

    sp = sub.add_parser("setup-telegram", help="Discover and save the Telegram chat id")
    sp.add_argument("--chat-id", help="Use this chat id directly")
    sp.set_defaults(func=cmd_setup_telegram)

    sp = sub.add_parser("list", help="List recent documents")
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

    sp = sub.add_parser("items", help="Show saved numbered items from the last list/search/monitor run")
    sp.add_argument("--source", choices=("any", "latest", "search", "monitor"), default="any")
    sp.set_defaults(func=cmd_items)

    sp = sub.add_parser("download", help="Download document attachment(s)")
    sp.add_argument("--module", choices=list(config.MODULES), default="den")
    sp.add_argument("--id", dest="ids", action="append", default=[],
                    help="Document intid; repeatable. Accepts module:id.")
    sp.add_argument("--item", dest="items", action="append", default=[],
                    help="Saved item number, comma-list, or range.")
    sp.add_argument("--all", action="store_true", help="Use every saved item.")
    sp.add_argument("--source", choices=("any", "latest", "search", "monitor"), default="any")
    sp.add_argument("--dest-dir", help="Download root directory")
    sp.add_argument("--lookup-limit", type=int, default=200,
                    help="Fallback recent-document lookup window")
    sp.set_defaults(func=cmd_download)

    sp = sub.add_parser("send", help="Download and send document attachment(s) via Telegram")
    sp.add_argument("--module", choices=list(config.MODULES), default="den")
    sp.add_argument("--id", dest="ids", action="append", default=[],
                    help="Document intid; repeatable. Accepts module:id.")
    sp.add_argument("--item", dest="items", action="append", default=[],
                    help="Saved item number, comma-list, or range.")
    sp.add_argument("--all", action="store_true", help="Use every saved item.")
    sp.add_argument("--source", choices=("any", "latest", "search", "monitor"), default="any")
    sp.add_argument("--dest-dir", help="Download root directory")
    sp.add_argument("--lookup-limit", type=int, default=200,
                    help="Fallback recent-document lookup window")
    sp.add_argument("--delete-after", action="store_true",
                    help="Delete local downloaded files after sending")
    sp.set_defaults(func=cmd_send)

    sp = sub.add_parser("monitor", help="Run one polling pass (fetch/alert)")
    sp.add_argument("--once", action="store_true", help="(default) single pass")
    sp.add_argument("--modules", type=_modules, default=config.DEFAULT_MODULES)
    sp.add_argument("--limit", type=int, default=60, help="Documents per page")
    sp.add_argument("--pages", type=int, default=config.DEFAULT_FETCH_PAGES,
                    help=f"Pages to fetch per module (default {config.DEFAULT_FETCH_PAGES})")
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
