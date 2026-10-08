from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse, Response

from app.api.deps import DbSession, require_api_key
from app.exceptions import CertificateNotReady
from app.models import CertificateStatus
from app.schemas import CertificateRead
from app.serializers import certificate_to_read
from app.services.jobs import get_certificate
from app.services.paths import resolve_stored_file
from app.services.preview_image import render_pdf_png

router = APIRouter(
    prefix="/certificates",
    tags=["certificates"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/{certificate_id}", response_model=CertificateRead, summary="Get one certificate")
def read_certificate(certificate_id: str, db: DbSession) -> CertificateRead:
    return certificate_to_read(get_certificate(db, certificate_id))


@router.get("/{certificate_id}/preview.png", summary="Preview a generated certificate")
def preview_certificate(certificate_id: str, db: DbSession) -> Response:
    certificate = get_certificate(db, certificate_id)
    if certificate.status != CertificateStatus.succeeded.value or not certificate.file_path:
        raise CertificateNotReady(certificate.status)
    path = resolve_stored_file(certificate.file_path)
    return Response(content=render_pdf_png(path), media_type="image/png")


@router.get("/{certificate_id}/download", summary="Download a generated PDF")
def download_certificate(
    certificate_id: str,
    db: DbSession,
    inline: bool = Query(default=False, description="Display the PDF in the browser instead of downloading it."),
) -> FileResponse:
    certificate = get_certificate(db, certificate_id)
    if certificate.status != CertificateStatus.succeeded.value or not certificate.file_path:
        raise CertificateNotReady(certificate.status)
    path = resolve_stored_file(certificate.file_path)
    filename = f"{certificate.certificate_number}.pdf"
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=filename,
        content_disposition_type="inline" if inline else "attachment",
    )
