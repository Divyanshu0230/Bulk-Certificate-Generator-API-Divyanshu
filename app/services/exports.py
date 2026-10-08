import csv
import io
import re
import zipfile

from app.models import Certificate, CertificateStatus, GenerationJob
from app.services.paths import resolve_stored_file
from app.utils import public_url

_UNSAFE_CSV_PREFIX = ("=", "+", "-", "@", "\t", "\r")


def build_archive(certificates: list[Certificate]) -> bytes:
    buffer = io.BytesIO()
    used_names: set[str] = set()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for certificate in certificates:
            if certificate.status != CertificateStatus.succeeded.value or not certificate.file_path:
                continue
            path = resolve_stored_file(certificate.file_path)
            filename = _archive_name(certificate, used_names)
            archive.write(path, arcname=filename)
    return buffer.getvalue()


def build_report(job: GenerationJob, certificates: list[Certificate]) -> str:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "position",
            "recipient_name",
            "recipient_email",
            "external_id",
            "detail",
            "status",
            "failure_stage",
            "error_message",
            "certificate_number",
            "event_title",
            "issuer",
            "issue_date",
            "verify_url",
            "download_url",
        ]
    )
    for certificate in certificates:
        number = certificate.certificate_number or ""
        ready = certificate.status == CertificateStatus.succeeded.value and bool(number)
        writer.writerow(
            [
                certificate.position,
                _csv_safe(certificate.recipient_name),
                _csv_safe(certificate.recipient_email or ""),
                _csv_safe(certificate.external_id or ""),
                _csv_safe(certificate.detail or ""),
                certificate.status,
                certificate.failure_stage or "",
                _csv_safe(certificate.error_message or ""),
                number,
                _csv_safe(job.event_title),
                _csv_safe(job.issuer),
                job.issue_date.isoformat(),
                public_url(f"/api/v1/verify/{number}") if ready else "",
                public_url(f"/api/v1/certificates/{certificate.id}/download") if ready else "",
            ]
        )
    return buffer.getvalue()


def succeeded(certificates: list[Certificate]) -> list[Certificate]:
    return [
        certificate
        for certificate in certificates
        if certificate.status == CertificateStatus.succeeded.value and certificate.file_path
    ]


def _archive_name(certificate: Certificate, used_names: set[str]) -> str:
    stem = re.sub(r"[^A-Za-z0-9]+", "-", certificate.recipient_name).strip("-")
    stem = (stem[:40] or "certificate")
    filename = f"{stem}-{certificate.certificate_number}.pdf"
    if filename in used_names:
        filename = f"{stem}-{certificate.position}-{certificate.certificate_number}.pdf"
    used_names.add(filename)
    return filename


def _csv_safe(value: str) -> str:
    if value.startswith(_UNSAFE_CSV_PREFIX):
        return "'" + value
    return value
