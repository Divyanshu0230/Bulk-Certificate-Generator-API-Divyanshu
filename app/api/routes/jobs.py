from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import JSONResponse, Response

from app.api.deps import DbSession, require_api_key
from app.exceptions import ArchiveNotReady
from app.models import CertificateStatus, JobStatus
from app.schemas import CertificateList, GenerateRequest, JobCreated, JobList, JobRead
from app.serializers import certificate_to_read, job_to_created, job_to_read
from app.services.exports import build_archive, build_report, succeeded
from app.services.hosted_state import generates_in_request
from app.services.jobs import (
    create_job,
    get_job,
    list_certificates,
    list_jobs,
    normalize_idempotency_key,
    process_job,
)

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    dependencies=[Depends(require_api_key)],
)


@router.post(
    "",
    response_model=JobCreated,
    status_code=202,
    summary="Create a bulk certificate job",
    responses={
        200: {"model": JobCreated, "description": "Idempotency key matched an existing job"},
        202: {"model": JobCreated, "description": "Job accepted and queued"},
    },
)
def create_generation_job(
    payload: GenerateRequest,
    db: DbSession,
    idempotency_key: Annotated[str | None, Header()] = None,
):
    """Accept a batch of recipients and queue certificate generation.

    Recipients that fail content checks are saved on the job as failed rows.
    Everyone else is generated in the background. Send ``Idempotency-Key`` to
    make a retry return the original job instead of creating a second one.
    """

    job, created = create_job(db, payload, normalize_idempotency_key(idempotency_key))
    if generates_in_request() and job.status == JobStatus.queued.value:
        process_job(db, job.id)
        db.expire_all()
        job = get_job(db, job.id)
    body = job_to_created(job).model_dump(mode="json")
    return JSONResponse(
        status_code=202 if created else 200,
        content=body,
        headers={"Location": f"/api/v1/jobs/{job.id}"},
    )


@router.get("", response_model=JobList, summary="List generation jobs")
def get_jobs(
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: JobStatus | None = None,
) -> JobList:
    rows, total = list_jobs(
        db,
        limit=limit,
        offset=offset,
        status=status.value if status else None,
    )
    return JobList(
        items=[job_to_read(job) for job in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}", response_model=JobRead, summary="Get job status and progress")
def get_generation_job(job_id: str, db: DbSession) -> JobRead:
    return job_to_read(get_job(db, job_id))


@router.get(
    "/{job_id}/certificates",
    response_model=CertificateList,
    summary="List certificates in a job",
)
def get_job_certificates(
    job_id: str,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: CertificateStatus | None = None,
) -> CertificateList:
    _job, rows, total = list_certificates(
        db,
        job_id,
        limit=limit,
        offset=offset,
        status=status.value if status else None,
    )
    return CertificateList(
        items=[certificate_to_read(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}/archive", summary="Download successful certificates as a zip")
def download_archive(job_id: str, db: DbSession) -> Response:
    job = get_job(db, job_id)
    ready = succeeded(list(job.certificates))
    if not ready:
        raise ArchiveNotReady()
    payload = build_archive(ready)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="certificates-{job.id}.zip"'},
    )


@router.get("/{job_id}/report", summary="Download a CSV report of every recipient")
def download_report(job_id: str, db: DbSession) -> Response:
    job = get_job(db, job_id)
    payload = build_report(job, list(job.certificates))
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="certificates-{job.id}.csv"'},
    )
