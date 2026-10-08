from pathlib import Path

from app.config import get_settings
from app.exceptions import CertificateFileMissing, CertificateNotFound


def storage_root() -> Path:
    return Path(get_settings().storage_dir).resolve()


def certificate_pdf_path(job_id: str, certificate_id: str) -> Path:
    directory = storage_root() / job_id
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{certificate_id}.pdf"


def resolve_stored_file(file_path: str) -> Path:
    """Return a certificate path only when it stays inside the storage directory."""

    root = storage_root()
    candidate = Path(file_path).resolve()
    if not candidate.is_relative_to(root):
        raise CertificateNotFound()
    if not candidate.is_file():
        from app.services.hosted_state import ensure_pdf

        ensure_pdf(candidate)
    if not candidate.is_file():
        raise CertificateFileMissing()
    return candidate
