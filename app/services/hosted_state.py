"""Shared disk for a host that does not keep one.

Locally the database and the PDFs stay on the machine, and a thread generates
certificates after the response. On Vercel the disk disappears between
requests and nothing keeps that thread alive, so the same files are stored in
Vercel Blob and generation runs inside the request that created the job.
"""

import logging
import os
from pathlib import Path

from app.config import get_settings
from app.database import engine

logger = logging.getLogger(__name__)

_DB_BLOB = "state/certificates.db"


def generates_in_request() -> bool:
    return os.environ.get("VERCEL") == "1"


def blob_enabled() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("BLOB_STORE_ID"))


def pull_database() -> None:
    if not blob_enabled():
        return
    path = _sqlite_file()
    if path is None:
        return
    payload = _download(_DB_BLOB)
    if payload is None:
        return
    engine.dispose()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(path) + suffix)
        if sidecar.exists():
            sidecar.unlink()


def push_state() -> None:
    if not blob_enabled():
        return
    path = _sqlite_file()
    if path is None or not path.is_file():
        return
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    _upload(_DB_BLOB, path.read_bytes(), "application/octet-stream")
    root = Path(get_settings().storage_dir).resolve()
    if not root.is_dir():
        return
    for pdf in root.rglob("*.pdf"):
        relative = pdf.relative_to(root).as_posix()
        _upload(f"pdfs/{relative}", pdf.read_bytes(), "application/pdf")


def ensure_pdf(path: Path) -> None:
    if path.is_file() or not blob_enabled():
        return
    root = Path(get_settings().storage_dir).resolve()
    try:
        relative = path.resolve().relative_to(root).as_posix()
    except ValueError:
        return
    payload = _download(f"pdfs/{relative}")
    if payload is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _sqlite_file() -> Path | None:
    url = get_settings().database_url
    if not url.startswith("sqlite:///"):
        return None
    raw = url.removeprefix("sqlite:///")
    if not raw or raw == ":memory:":
        return None
    return Path(raw)


def _client():
    from vercel.blob import BlobClient

    return BlobClient()


def _download(pathname: str) -> bytes | None:
    from vercel.blob import BlobNotFoundError

    try:
        result = _client().get(pathname, access="private", use_cache=False)
    except BlobNotFoundError:
        return None
    if result is None or not result.content:
        return None
    return result.content


def _upload(pathname: str, body: bytes, content_type: str) -> None:
    _client().put(
        pathname,
        body,
        access="private",
        content_type=content_type,
        overwrite=True,
        add_random_suffix=False,
    )
    logger.info("Stored %s (%s bytes)", pathname, len(body))
