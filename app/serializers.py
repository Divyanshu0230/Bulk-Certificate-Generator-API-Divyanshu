import json

from app.models import Certificate, CertificateStatus, GenerationJob
from app.schemas import (
    CertificateRead,
    EventOut,
    JobCreated,
    JobLinks,
    JobRead,
    Progress,
    RecipientIssue,
    Verification,
)
from app.utils import as_utc, public_url


def job_to_read(job: GenerationJob) -> JobRead:
    resolved = job.success_count + job.failure_count
    percent = 0 if job.total_count == 0 else (resolved * 100) // job.total_count
    return JobRead(
        id=job.id,
        status=job.status,
        event=EventOut(
            title=job.event_title,
            issuer=job.issuer,
            issue_date=job.issue_date,
            description=job.description,
            signatory_name=job.signatory_name,
            signatory_title=job.signatory_title,
        ),
        progress=Progress(
            total=job.total_count,
            pending=job.pending_count,
            succeeded=job.success_count,
            failed=job.failure_count,
            percent_complete=percent,
        ),
        callback_url=job.callback_url,
        error_message=job.error_message,
        created_at=as_utc(job.created_at),
        started_at=as_utc(job.started_at),
        completed_at=as_utc(job.completed_at),
        links=JobLinks(
            self=public_url(f"/api/v1/jobs/{job.id}"),
            certificates=public_url(f"/api/v1/jobs/{job.id}/certificates"),
            archive=public_url(f"/api/v1/jobs/{job.id}/archive"),
            report=public_url(f"/api/v1/jobs/{job.id}/report"),
        ),
    )


def job_to_created(job: GenerationJob) -> JobCreated:
    return JobCreated(
        **job_to_read(job).model_dump(),
        validation_issues=validation_issues(job),
    )


def validation_issues(job: GenerationJob) -> list[RecipientIssue]:
    issues: list[RecipientIssue] = []
    for certificate in sorted(job.certificates, key=lambda item: item.position):
        if not certificate.error_detail:
            continue
        try:
            parsed = json.loads(certificate.error_detail)
        except json.JSONDecodeError:
            continue
        for item in parsed:
            issues.append(
                RecipientIssue(
                    position=certificate.position,
                    field=item["field"],
                    message=item["message"],
                )
            )
    return issues


def certificate_to_read(certificate: Certificate) -> CertificateRead:
    ready = certificate.status == CertificateStatus.succeeded.value and bool(
        certificate.certificate_number
    )
    return CertificateRead(
        id=certificate.id,
        job_id=certificate.job_id,
        position=certificate.position,
        recipient_name=certificate.recipient_name,
        recipient_email=certificate.recipient_email,
        external_id=certificate.external_id,
        detail=certificate.detail,
        status=certificate.status,
        failure_stage=certificate.failure_stage,
        error_message=certificate.error_message,
        certificate_number=certificate.certificate_number,
        created_at=as_utc(certificate.created_at),
        generated_at=as_utc(certificate.generated_at),
        download_url=(
            public_url(f"/api/v1/certificates/{certificate.id}/download") if ready else None
        ),
        verify_url=(
            public_url(f"/api/v1/verify/{certificate.certificate_number}") if ready else None
        ),
    )


def verification_from(certificate: Certificate) -> Verification:
    job = certificate.job
    return Verification(
        certificate_number=certificate.certificate_number or "",
        recipient_name=certificate.recipient_name,
        event_title=job.event_title,
        issuer=job.issuer,
        issue_date=job.issue_date,
        description=job.description,
        detail=certificate.detail,
    )
