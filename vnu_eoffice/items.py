"""Persist and render numbered document selections for follow-up actions."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Iterable, Sequence

from . import config
from .documents import DocumentRef, parse_document_refs
from .models import Document


def save_mapping(
    source: str,
    docs: Sequence[Document],
    query: str = "",
    modules: Sequence[str] = config.DEFAULT_MODULES,
    path: Path | None = None,
) -> None:
    payload = {
        "source": source,
        "query": query,
        "modules": list(modules),
        "created_at": int(time.time()),
        "items": [
            {
                "index": index,
                "module": doc.module,
                "intid": doc.intid,
                "key": doc.key,
                "date": doc.date,
                "number": doc.number,
                "symbol": doc.symbol,
                "subject": doc.subject,
                "party": doc.party,
                "has_attach": doc.has_attach,
            }
            for index, doc in enumerate(docs, start=1)
        ],
    }
    config.write_private_text(path or config.ITEMS_FILE, json.dumps(payload, ensure_ascii=False, indent=2))


def load_mapping(source: str = "any", path: Path | None = None) -> dict:
    mapping_path = path or config.ITEMS_FILE
    try:
        payload = json.loads(mapping_path.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError("No saved document items. Run list, search, or monitor first.") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Saved document item mapping is corrupt. Run list, search, or monitor again.") from exc
    if source != "any" and payload.get("source") != source:
        raise RuntimeError(f"Saved item mapping is from {payload.get('source')!r}, not {source!r}.")
    return payload


def format_mapping_listing(payload: dict, title: str = "VNU eOffice saved item numbers") -> str:
    source = payload.get("source") or "unknown"
    query = payload.get("query") or ""
    modules = tuple(payload.get("modules") or config.DEFAULT_MODULES)
    items = payload.get("items") or []
    lines = [title, "", f"Source: {source}"]
    if query:
        lines.append(f"Query: {query}")
    if not items:
        lines.append("No saved items.")
        return "\n".join(lines)
    lines.append("Use these item numbers for follow-up downloads.")
    by_module: dict[str, list[dict]] = {module: [] for module in modules}
    for item in items:
        by_module.setdefault(str(item.get("module")), []).append(item)
    for module in modules:
        lines.append("")
        lines.append(module_heading(module))
        module_items = by_module.get(module, [])
        if not module_items:
            lines.append("   No saved items in this category.")
            continue
        for item in module_items:
            meta = format_meta(
                str(item.get("key") or f"{item.get('module')}:{item.get('intid')}"),
                str(item.get("date") or "-")[:10],
                str(item.get("symbol") or item.get("number") or "-"),
                bool(item.get("has_attach")),
            )
            lines.append(f"{item.get('index')}. {meta}")
            party = item.get("party")
            if party:
                lines.append(f"   Unit: {short(party, 120)}")
            lines.append(f"   Subject: {short(item.get('subject'), 220)}")
    return "\n".join(lines)


def format_listing(title: str, summary: str, docs: Sequence[Document], modules: Sequence[str]) -> str:
    lines = [title, "", summary, "", "Scan"]
    for module in modules:
        lines.append(f"- {module_heading(module)}")
    if not docs:
        lines.append("")
        lines.append("No documents found.")
        return "\n".join(lines)
    lines.append("")
    lines.append("Follow-up")
    lines.append("Use these item numbers for follow-up downloads.")
    lines.extend(format_numbered_documents(docs, modules))
    return "\n".join(lines)


def format_monitor_result(result, modules: Sequence[str], title: str = "VNU eOffice monitor") -> str:
    lines = [
        title,
        "",
        "Status",
    ]
    if result.first_run and result.baseline_modules:
        lines.extend([
            f"- Baseline recorded: {result.baseline_count} document(s) in view.",
            f"- Modules initialized: {', '.join(result.baseline_modules)}.",
            "- Alerts: none on first run.",
        ])
    else:
        lines.extend([
            f"- New documents: {result.new_count}",
            f"- Alerts: {len(result.alerts)}",
            f"- Errors: {len(result.errors)}",
        ])
        if result.baseline_modules:
            lines.append(f"- Newly baselined modules: {', '.join(result.baseline_modules)}")

    lines.append("")
    lines.append("Scan")
    for module in modules:
        lines.append(f"- {module_heading(module)}")

    if result.alerts:
        lines.append("")
        lines.append("Follow-up")
        lines.append("- Alert item numbers were saved. Ask for item numbers to download files.")
        lines.extend(format_numbered_documents([alert.doc for alert in result.alerts], modules))
    else:
        lines.append("")
        lines.append("No alert items in this run.")

    if result.errors:
        lines.append("")
        lines.append("Errors")
        for error in result.errors:
            lines.append(f"- {error}")
    return "\n".join(lines)


def format_numbered_documents(docs: Sequence[Document], modules: Sequence[str]) -> list[str]:
    lines: list[str] = []
    by_module: dict[str, list[tuple[int, Document]]] = {module: [] for module in modules}
    for index, doc in enumerate(docs, start=1):
        by_module.setdefault(doc.module, []).append((index, doc))
    for module in modules:
        lines.append("")
        lines.append(module_heading(module))
        items = by_module.get(module, [])
        if not items:
            lines.append("   No documents found in this category.")
            continue
        for index, doc in items:
            lines.append(
                f"{index}. {format_meta(doc.key, doc.date_short or '-', doc.symbol or doc.number or '-', doc.has_attach)}"
            )
            if doc.party:
                lines.append(f"   Unit: {short(doc.party, 120)}")
            lines.append(f"   Subject: {short(doc.subject, 220)}")
    return lines


def resolve_document_refs(
    ids: Sequence[str] | None = None,
    items: Sequence[str] | None = None,
    all_items: bool = False,
    source: str = "any",
    default_module: str = "den",
) -> list[DocumentRef]:
    refs: list[DocumentRef] = []
    if ids:
        refs.extend(parse_document_refs(ids, default_module=default_module))
    if all_items or items:
        payload = load_mapping(source)
        saved_items = payload.get("items") or []
        if all_items:
            chosen = saved_items
        else:
            wanted = parse_indices(items or [])
            by_index = {int(item["index"]): item for item in saved_items}
            missing = [idx for idx in wanted if idx not in by_index]
            if missing:
                raise RuntimeError(f"Saved item number(s) not found: {', '.join(map(str, missing))}")
            chosen = [by_index[idx] for idx in wanted]
        refs.extend(DocumentRef(str(item["module"]), str(item["intid"])) for item in chosen)
    refs = dedupe_refs(refs)
    if not refs:
        raise RuntimeError("No documents selected. Use --id, --item, or --all.")
    return refs


def parse_indices(values: Sequence[str]) -> list[int]:
    indices: list[int] = []
    for raw in values:
        for part in str(raw).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start_s, end_s = (piece.strip() for piece in part.split("-", 1))
                start, end = int(start_s), int(end_s)
                if start < 1 or end < start:
                    raise ValueError(f"Invalid item range: {part}")
                indices.extend(range(start, end + 1))
            else:
                value = int(part)
                if value < 1:
                    raise ValueError(f"Invalid item number: {part}")
                indices.append(value)
    return dedupe_ints(indices)


def top_latest(docs: Iterable[Document], limit: int) -> list[Document]:
    return sorted(docs, key=lambda doc: doc.date or "", reverse=True)[:limit]


def top_by_module(docs: Iterable[Document], modules: Sequence[str], limit: int) -> list[Document]:
    grouped = {module: [] for module in modules}
    for doc in docs:
        grouped.setdefault(doc.module, []).append(doc)
    out: list[Document] = []
    for module in modules:
        out.extend(top_latest(grouped.get(module, []), limit))
    return out


def format_download_summary(downloaded, sent: bool, deleted: bool, title: str = "VNU eOffice document delivery") -> str:
    files_count = sum(len(item.files) for item in downloaded)
    action = "sent" if sent else "downloaded"
    lines = [
        title,
        "",
        "Status",
        f"- Documents {action}: {len(downloaded)}",
        f"- Files: {files_count}",
        f"- Local copies deleted: {'yes' if deleted else 'no'}",
    ]
    for item in downloaded:
        lines.append(f"- {item.doc.key} | files={len(item.files)} | {short(item.doc.subject, 160)}")
    return "\n".join(lines)


def format_meta(key: str, date: str, symbol: str, has_attach: bool) -> str:
    files = "yes" if has_attach else "no"
    return f"ID: {key} | Date: {date or '-'} | Ref: {symbol or '-'} | Files: {files}"


def module_heading(module: str) -> str:
    label = config.MODULES.get(module, {}).get("label", module)
    english = "Incoming" if module == "den" else "Outgoing" if module == "di" else module
    return f"{english} ({module}) - {label}"


def split_text(text: str, limit: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines() or [""]:
        addition = len(line) + 1
        if current and current_len + addition > limit:
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        if len(line) > limit:
            if current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            chunks.extend(line[i:i + limit] for i in range(0, len(line), limit))
            continue
        current.append(line)
        current_len += addition
    if current:
        chunks.append("\n".join(current))
    return chunks


def remove_leading_title(text: str, title: str) -> str:
    text = str(text or "")
    if text.startswith(title):
        return text[len(title):].lstrip("\n")
    return text


def dedupe_refs(refs: Iterable[DocumentRef]) -> list[DocumentRef]:
    seen: set[tuple[str, str]] = set()
    out: list[DocumentRef] = []
    for ref in refs:
        key = (ref.module, ref.intid)
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
    return out


def dedupe_ints(values: Iterable[int]) -> list[int]:
    seen: set[int] = set()
    out: list[int] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def short(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
