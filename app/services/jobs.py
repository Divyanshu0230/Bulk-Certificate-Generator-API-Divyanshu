import hashlib
import json
import logging
import re
import secrets
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.constants import DEFAULT_DESCRIPTION, DEFAULT_SIGNATORY_TITLE
from app.exceptions import (
    CertificateNotFound,
    CertificateRenderError,
    IdempotencyConflict,
    InvalidIdempotencyKey,
    JobNotFound,
    NoValidRecipients,
    TooManyRecipients,
)
from app.models import (
    TERMINAL_JOB_STATUSES,
    Certificate,
    CertificateStatus,
    FailureStage,
    GenerationJob,
    JobStatus,
)
from app.schemas import GenerateRequest
from app.services.callbacks import deliver_callback
from app.services.pdf import render_certificate
from app.services.paths import certificate_pdf_path
from app.services.validation import validate_recipients
from app.utils import public_url, utcnow

logger = logging.getLogger(__name__)

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:\-]{1,200}$")


def normalize_idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = value.strip()
    if not key:
        return None
    if _IDEMPOTENCY_KEY.fullmatch(key) is None:
        raise InvalidIdempotencyKey()
    return key


def create_job(
    db: Session,
    payload: GenerateRequest,
    idempotency_key: str | None,
) -> tuple[GenerationJob, bool]:
    """Persist a job and return ``(job, created)``.

    A repeated ``Idempotency-Key`` with the same body returns the original job
    instead of generating a second batch. Invalid recipients are stored as
    failed rows. Valid recipients stay pending for the worker.
    """

    fingerprint = _fingerprint(payload)
    if idempotency_key:
        existing = db.scalar(
            select(GenerationJob).where(GenerationJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if existing.payload_hash != fingerprint:
                raise IdempotencyConflict()
            return existing, False

    limit = get_settings().max_recipients_per_job
    if len(payload.recipients) > limit:
        raise TooManyRecipients(limit)

    drafts = validate_recipients(payload.recipients)
    valid_count = sum(1 for draft in drafts if draft.is_valid)
    if valid_count == 0:
        raise NoValidRecipients(
            errors=[
                {"position": issue.position, "field": issue.field, "message": issue.message}
                for draft in drafts
                for issue in draft.issues
            ]
        )

    description = payload.event.description or DEFAULT_DESCRIPTION
    job = GenerationJob(
        id=str(uuid.uuid4()),
        status=JobStatus.queued.value,
        event_title=payload.event.title,
        issuer=payload.event.issuer,
        issue_date=payload.event.issue_date,
        description=description,
        signatory_name=payload.event.signatory_name,
        signatory_title=payload.event.signatory_title,
        callback_url=str(payload.callback_url) if payload.callback_url else None,
        idempotency_key=idempotency_key,
        payload_hash=fingerprint,
        total_count=len(drafts),
        pending_count=valid_count,
        success_count=0,
        failure_count=len(drafts) - valid_count,
    )
    db.add(job)

    for draft in drafts:
        certificate = Certificate(
            id=str(uuid.uuid4()),
            job_id=job.id,
            position=draft.position,
            recipient_name=draft.name,
            recipient_email=draft.email,
            external_id=draft.external_id,
            detail=draft.detail,
            status=(
                CertificateStatus.pending.value
                if draft.is_valid
                else CertificateStatus.failed.value
            ),
            failure_stage=None if draft.is_valid else FailureStage.validation.value,
            error_message="; ".join(issue.message for issue in draft.issues) or None,
            error_detail=(
                json.dumps(
                    [{"field": issue.field, "message": issue.message} for issue in draft.issues]
                )
                if draft.issues
                else None
            ),
        )
        job.certificates.append(certificate)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if idempotency_key:
            existing = db.scalar(
                select(GenerationJob).where(GenerationJob.idempotency_key == idempotency_key)
            )
            if existing is not None and existing.payload_hash == fingerprint:
                return existing, False
        raise
    return job, True


def get_job(db: Session, job_id: str) -> GenerationJob:
    job = db.get(GenerationJob, job_id)
    if job is None:
        raise JobNotFound()
    return job


def list_jobs(
    db: Session,
    *,
    limit: int,
    offset: int,
    status: str | None,
) -> tuple[list[GenerationJob], int]:
    statement = select(GenerationJob)
    count_statement = select(func.count()).select_from(GenerationJob)
    if status is not None:
        statement = statement.where(GenerationJob.status == status)
        count_statement = count_statement.where(GenerationJob.status == status)
    total = int(db.scalar(count_statement) or 0)
    rows = list(
        db.scalars(
            statement.order_by(GenerationJob.created_at.desc()).limit(limit).offset(offset)
        ).all()
    )
    return rows, total


def list_certificates(
    db: Session,
    job_id: str,
    *,
    limit: int,
    offset: int,
    status: str | None,
) -> tuple[GenerationJob, list[Certificate], int]:
    job = get_job(db, job_id)
    statement = select(Certificate).where(Certificate.job_id == job_id)
    count_statement = (
        select(func.count()).select_from(Certificate).where(Certificate.job_id == job_id)
    )
    if status is not None:
        statement = statement.where(Certificate.status == status)
        count_statement = count_statement.where(Certificate.status == status)
    total = int(db.scalar(count_statement) or 0)
    rows = list(
        db.scalars(statement.order_by(Certificate.position.asc()).limit(limit).offset(offset)).all()
    )
    return job, rows, total


def get_certificate(db: Session, certificate_id: str) -> Certificate:
    certificate = db.get(Certificate, certificate_id)
    if certificate is None:
        raise CertificateNotFound()
    return certificate


def requeue_interrupted_jobs(db: Session) -> int:
    """Move jobs left in ``processing`` back to ``queued``.

    Each certificate is committed on its own, so a restart continues with the
    rows that are still pending and leaves finished PDFs in place.
    """

    jobs = list(
        db.scalars(
            select(GenerationJob).where(GenerationJob.status == JobStatus.processing.value)
        ).all()
    )
    for job in jobs:
        job.status = JobStatus.queued.value
        job.started_at = None
        logger.warning("Requeued interrupted job %s", job.id)
    db.commit()
    return len(jobs)


def claim_queued_job(db: Session, job_id: str) -> bool:
    """Move one queued job to ``processing`` with a conditional update.

    Several workers may read the same id. The ``status = queued`` condition
    lets only one of those updates match, so the others leave the job alone.
    """

    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.id == job_id,
            GenerationJob.status == JobStatus.queued.value,
        )
        .values(status=JobStatus.processing.value, started_at=utcnow())
    )
    db.commit()
    return result.rowcount == 1


def process_job(db: Session, job_id: str) -> bool:
    """Generate every pending certificate for one job.

    A failure is stored on that certificate and the loop continues. Progress
    counts are committed after each recipient, so a poll can see partial work
    before the job is finished. Returns False when this caller did not claim
    the job.
    """

    if not claim_queued_job(db, job_id):
        return False
    try:
        _process_job(db, job_id)
    except Exception:
        logger.exception("Job %s stopped unexpectedly", job_id)
        db.rollback()
        job = db.get(GenerationJob, job_id)
        if job is not None and job.status not in TERMINAL_JOB_STATUSES:
            job.status = JobStatus.failed.value
            job.error_message = (
                "The job stopped unexpectedly. Certificates already generated are still available."
            )
            job.completed_at = utcnow()
            db.commit()
            deliver_callback(job)
        return True
    return True


def _process_job(db: Session, job_id: str) -> None:
    job = db.get(GenerationJob, job_id)
    if job is None:
        return
    db.refresh(job)
    if job.status in TERMINAL_JOB_STATUSES:
        return
    if job.status == JobStatus.queued.value:
        job.status = JobStatus.processing.value
        job.started_at = utcnow()
        db.commit()

    pending = list(
        db.scalars(
            select(Certificate)
            .where(
                Certificate.job_id == job_id,
                Certificate.status == CertificateStatus.pending.value,
            )
            .order_by(Certificate.position.asc())
        ).all()
    )
    for certificate in pending:
        _generate_one(db, job, certificate)
        db.commit()

    job.status = _final_status(job)
    job.completed_at = utcnow()
    db.commit()
    logger.info(
        "Job %s finished with status %s (succeeded=%s failed=%s)",
        job.id,
        job.status,
        job.success_count,
        job.failure_count,
    )
    deliver_callback(job)


def _generate_one(db: Session, job: GenerationJob, certificate: Certificate) -> None:
    path = None
    try:
        number = _allocate_number(db, job.issue_date.year)
        path = certificate_pdf_path(job.id, certificate.id)
        render_certificate(
            destination=path,
            recipient_name=certificate.recipient_name,
            event_title=job.event_title,
            issuer=job.issuer,
            issue_date=job.issue_date,
            description=job.description,
            detail=certificate.detail,
            certificate_number=number,
            verify_url=public_url(f"/api/v1/verify/{number}"),
            signatory_name=job.signatory_name or job.issuer,
            signatory_title=job.signatory_title or DEFAULT_SIGNATORY_TITLE,
        )
    except CertificateRenderError as exc:
        _mark_generation_failed(job, certificate, str(exc), path)
        return
    except Exception:
        logger.exception(
            "Unexpected certificate failure job=%s position=%s",
            job.id,
            certificate.position,
        )
        _mark_generation_failed(
            job,
            certificate,
            "Unexpected error while generating the certificate",
            path,
        )
        return

    certificate.status = CertificateStatus.succeeded.value
    certificate.certificate_number = number
    certificate.file_path = str(path)
    certificate.generated_at = utcnow()
    job.success_count += 1
    if job.pending_count > 0:
        job.pending_count -= 1


def _mark_generation_failed(job: GenerationJob, certificate: Certificate, message: str, path) -> None:
    if path is not None and path.exists():
        path.unlink()
    certificate.status = CertificateStatus.failed.value
    certificate.failure_stage = FailureStage.generation.value
    certificate.error_message = message[:500]
    certificate.certificate_number = None
    certificate.file_path = None
    job.failure_count += 1
    if job.pending_count > 0:
        job.pending_count -= 1


def _final_status(job: GenerationJob) -> str:
    if job.success_count and job.failure_count:
        return JobStatus.completed_with_errors.value
    if job.success_count:
        return JobStatus.completed.value
    return JobStatus.failed.value


def _allocate_number(db: Session, year: int) -> str:
    for _ in range(5):
        number = f"CERT-{year}-{secrets.token_hex(6).upper()}"
        taken = db.scalar(select(Certificate.id).where(Certificate.certificate_number == number))
        if taken is None:
            return number
    raise CertificateRenderError("Could not allocate a unique certificate number")


def _fingerprint(payload: GenerateRequest) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def claim_next_job_id(db: Session) -> str | None:
    statement = (
        select(GenerationJob.id)
        .where(GenerationJob.status == JobStatus.queued.value)
        .order_by(GenerationJob.created_at.asc())
        .limit(1)
    )
    # A Postgres deployment can run several workers. SKIP LOCKED stops them
    # from claiming the same queued job. SQLite is the single-worker local path.
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    return db.scalar(statement)
