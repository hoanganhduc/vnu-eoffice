"""vnu_eoffice — automate retrieval and alerting for the VNU e-office.

Targets the SELAB NetOffice document system at https://eoffice.vnu.edu.vn/qlvb/.
Handles both "Văn bản đến" (incoming) and "Văn bản đi" (outgoing) modules.
"""
from .models import Document
from .client import VnuClient
from .documents import (
    DocumentRef,
    DownloadedDocument,
    download_documents,
    fetch_documents,
    search_documents,
    send_documents,
)
from .notify import TelegramNotifier

__version__ = "0.1.0"
__all__ = [
    "Document",
    "VnuClient",
    "DocumentRef",
    "DownloadedDocument",
    "download_documents",
    "fetch_documents",
    "search_documents",
    "send_documents",
    "TelegramNotifier",
]
