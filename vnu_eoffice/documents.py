"""Direct document search, download, and Telegram sending helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from . import config
from .client import VnuClient, _safe_name
from .models import Document
from .notify import TelegramNotifier, esc


class DocumentNotFound(RuntimeError):
    pass


@dataclass(frozen=True)
class DocumentRef:
    module: str
    intid: str


@dataclass
class DownloadedDocument:
    doc: Document
    files: list[Path] = field(default_factory=list)


def parse_document_refs(refs: Sequence[str], default_module: str = "den") -> list[DocumentRef]:
    """Parse CLI-style document refs: ``123``, ``den:123``, ``di:456``."""
    if default_module not in config.MODULES:
        raise ValueError(f"Unknown module {default_module!r}; expected one of {list(config.MODULES)}")
    parsed: list[DocumentRef] = []
    for raw in refs:
        for part in str(raw).split(","):
            value = part.strip()
            if not value:
                continue
            if ":" in value:
                module, intid = (x.strip() for x in value.split(":", 1))
            else:
                module, intid = default_module, value
            if module not in config.MODULES:
                raise ValueError(f"Unknown module {module!r}; expected one of {list(config.MODULES)}")
            if not intid:
                raise ValueError("Document id must not be empty.")
            parsed.append(DocumentRef(module=module, intid=intid))
    if not parsed:
        raise ValueError("At least one document id is required.")
    return parsed


def search_documents(
    client: VnuClient,
    keywords: str,
    modules: tuple[str, ...] = config.DEFAULT_MODULES,
    limit: int = 20,
    pages: int = config.DEFAULT_FETCH_PAGES,
    unread_only: bool = False,
    has_attach: bool = False,
) -> list[Document]:
    """Search document subjects across one or more modules."""
    query = " ".join(str(keywords).split())
    if not query:
        raise ValueError("Search keywords must not be empty.")
    if not modules:
        raise ValueError("At least one module must be selected.")

    matches: list[Document] = []
    for module in modules:
        _, docs = fetch_documents(
            client,
            module,
            limit=limit,
            pages=pages,
            search=query,
            unread_only=unread_only,
            has_attach=has_attach,
        )
        matches.extend(docs)
    return matches


def fetch_documents(
    client: VnuClient,
    module: str,
    limit: int = 20,
    pages: int = config.DEFAULT_FETCH_PAGES,
    search: str = "",
    unread_only: bool = False,
    has_attach: bool = False,
    **extra,
) -> tuple[int, list[Document]]:
    """Fetch one or more pages from a document list endpoint."""
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    if pages < 1:
        raise ValueError("pages must be at least 1.")

    total = 0
    docs: list[Document] = []
    seen: set[str] = set()
    for page in range(1, pages + 1):
        total, page_docs = client.list_documents(
            module,
            page=page,
            limit=limit,
            search=search,
            unread_only=unread_only,
            has_attach=has_attach,
            **extra,
        )
        if not page_docs:
            break
        new_docs = [doc for doc in page_docs if doc.key not in seen]
        if not new_docs:
            break
        docs.extend(new_docs)
        seen.update(doc.key for doc in new_docs)
        if total and len(docs) >= total:
            break
        if len(page_docs) < limit:
            break
    return total, docs


def find_document_by_id(
    client: VnuClient,
    module: str,
    intid: str,
    lookup_limit: int = 200,
) -> Document:
    """Resolve one document id in a module, preferring the server id filter."""
    intid = str(intid)
    _, docs = client.list_documents(module, limit=1, intid=intid)
    match = _find_in_docs(docs, intid)
    if match:
        return match

    _, docs = client.list_documents(module, limit=lookup_limit)
    match = _find_in_docs(docs, intid)
    if match:
        return match
    raise DocumentNotFound(f"Document {module}:{intid} was not found in the latest {lookup_limit} records.")


def download_documents(
    client: VnuClient,
    refs: Iterable[DocumentRef],
    dest_dir: Path | None = None,
    lookup_limit: int = 200,
) -> list[DownloadedDocument]:
    """Download all attachments for the referenced documents."""
    downloaded: list[DownloadedDocument] = []
    for ref in refs:
        doc = find_document_by_id(client, ref.module, ref.intid, lookup_limit=lookup_limit)
        target = _document_dest_dir(dest_dir, doc) if dest_dir else None
        downloaded.append(DownloadedDocument(doc=doc, files=client.download_all(doc, target)))
    return downloaded


def send_documents(
    client: VnuClient,
    notifier: TelegramNotifier,
    refs: Iterable[DocumentRef],
    delete_after: bool = False,
    dest_dir: Path | None = None,
    lookup_limit: int = 200,
) -> list[DownloadedDocument]:
    """Download referenced documents and send their attachments via Telegram."""
    downloaded = download_documents(client, refs, dest_dir=dest_dir, lookup_limit=lookup_limit)
    try:
        for item in downloaded:
            notifier.send_message(_format_document_message(item.doc, item.files))
            for path in item.files:
                notifier.send_document(path, caption=_caption(item.doc))
        return downloaded
    finally:
        if delete_after:
            _delete_files(path for item in downloaded for path in item.files)


def _find_in_docs(docs: Iterable[Document], intid: str) -> Document | None:
    return next((doc for doc in docs if doc.intid == intid), None)


def _document_dest_dir(root: Path | None, doc: Document) -> Path | None:
    if root is None:
        return None
    return Path(root) / doc.module / f"{_safe_name(doc.number or '0')}_{_safe_name(doc.intid)}"


def _format_document_message(doc: Document, files: list[Path]) -> str:
    lines = [
        f"<b>{esc(doc.module_label)}</b>",
        f"<b>ID:</b> {esc(doc.intid)}",
        f"<b>So:</b> {esc(doc.number)}",
    ]
    if doc.symbol:
        lines.append(f"<b>Ky hieu:</b> {esc(doc.symbol)}")
    if doc.date_short:
        lines.append(f"<b>Ngay:</b> {esc(doc.date_short)}")
    if doc.party:
        lines.append(f"<b>Don vi:</b> {esc(doc.party)}")
    lines.append(f"<b>Trich yeu:</b> {esc(doc.subject)}")
    lines.append(f"<b>Attachments:</b> {len(files)}")
    lines.append(f'<a href="{esc(doc.web_url())}">Open in e-office</a>')
    return "\n".join(lines)


def _caption(doc: Document) -> str:
    text = f"{doc.symbol or doc.number} - {doc.subject}".strip(" -")
    return text[:1024]


def _delete_files(files: Iterable[Path]) -> None:
    dirs: set[Path] = set()
    for path in files:
        path = Path(path)
        try:
            path.unlink(missing_ok=True)
            dirs.add(path.parent)
        except OSError:
            pass
    for directory in dirs:
        try:
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()
        except OSError:
            pass
