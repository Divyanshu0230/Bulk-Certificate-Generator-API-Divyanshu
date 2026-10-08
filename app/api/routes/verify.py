from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.api.deps import DbSession
from app.constants import CERTIFICATE_NUMBER_RE
from app.exceptions import CertificateNotFound
from app.models import Certificate, CertificateStatus
from app.schemas import Verification
from app.serializers import verification_from
from app.services.verify_page import not_found_page, verification_page

router = APIRouter(prefix="/verify", tags=["verification"])


@router.get(
    "/{certificate_number}",
    response_model=Verification,
    summary="Verify a certificate number",
    responses={404: {"description": "No issued certificate uses this number"}},
)
def verify_certificate(certificate_number: str, request: Request, db: DbSession):
    """Public lookup used by the QR code printed on each certificate.

    The response includes the name and event, and omits email and the caller's
    external id. Browsers receive a small HTML page; API clients receive JSON.
    """

    certificate = _find_issued(db, certificate_number)
    if _wants_html(request):
        if certificate is None:
            return HTMLResponse(not_found_page(), status_code=404)
        return HTMLResponse(verification_page(verification_from(certificate)))
    if certificate is None:
        raise CertificateNotFound()
    return verification_from(certificate)


def _find_issued(db, certificate_number: str) -> Certificate | None:
    if CERTIFICATE_NUMBER_RE.fullmatch(certificate_number) is None:
        return None
    return db.scalar(
        select(Certificate).where(
            Certificate.certificate_number == certificate_number,
            Certificate.status == CertificateStatus.succeeded.value,
        )
    )


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    for part in accept.split(","):
        media = part.split(";", 1)[0].strip().lower()
        if media == "application/json":
            return False
        if media == "text/html":
            return True
    return False
