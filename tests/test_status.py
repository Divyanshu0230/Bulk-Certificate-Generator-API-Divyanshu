from sqlalchemy import select

from app.database import SessionLocal
from app.models import CertificateStatus, GenerationJob, JobStatus
from app.services.jobs import claim_queued_job, requeue_interrupted_jobs
from app.services.pdf import render_certificate
from app.services.worker import process_next_job
from tests.conftest import payload, recipient, run_queued_jobs


def test_job_status_reports_progress(client):
    created = client.post(
        "/api/v1/jobs",
        json=payload(
            [
                recipient("Ada Lovelace"),
                recipient("Alan Turing"),
                recipient("Grace Hopper"),
            ]
        ),
    )
    job_id = created.json()["id"]

    queued = client.get(f"/api/v1/jobs/{job_id}").json()
    assert queued["status"] == "queued"
    assert queued["progress"]["pending"] == 3
    assert queued["progress"]["percent_complete"] == 0

    run_queued_jobs()
    done = client.get(f"/api/v1/jobs/{job_id}").json()
    assert done["status"] == "completed"
    assert done["progress"] == {
        "total": 3,
        "pending": 0,
        "succeeded": 3,
        "failed": 0,
        "percent_complete": 100,
    }

    again = process_next_job()
    assert again is False
    repeated = client.get(f"/api/v1/jobs/{job_id}").json()
    assert repeated["progress"]["succeeded"] == 3


def test_progress_is_visible_before_the_job_finishes(client, monkeypatch):
    observations = []
    real_render = render_certificate

    def spy(**kwargs):
        db = SessionLocal()
        try:
            job = db.scalars(select(GenerationJob)).one()
            observations.append((job.status, job.success_count, job.pending_count))
        finally:
            db.close()
        real_render(**kwargs)

    monkeypatch.setattr("app.services.jobs.render_certificate", spy)
    created = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Ada Lovelace"), recipient("Alan Turing")]),
    )
    run_queued_jobs()

    assert observations[0] == (JobStatus.processing.value, 0, 2)
    assert observations[1] == (JobStatus.processing.value, 1, 1)
    finished = client.get(f"/api/v1/jobs/{created.json()['id']}").json()
    assert finished["status"] == "completed"


def test_interrupted_job_is_requeued_and_then_finished(client):
    created = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Ada Lovelace"), recipient("Alan Turing")]),
    )
    job_id = created.json()["id"]

    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        job.status = JobStatus.processing.value
        db.commit()
        assert requeue_interrupted_jobs(db) == 1
        db.refresh(job)
        assert job.status == JobStatus.queued.value
    finally:
        db.close()

    assert process_next_job() is True
    finished = client.get(f"/api/v1/jobs/{job_id}").json()
    assert finished["status"] == "completed"
    assert finished["progress"]["succeeded"] == 2


def test_resume_does_not_regenerate_a_finished_certificate(client, monkeypatch):
    calls = {"count": 0}
    real_render = render_certificate

    def counting(**kwargs):
        calls["count"] += 1
        real_render(**kwargs)

    monkeypatch.setattr("app.services.jobs.render_certificate", counting)
    created = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Ada Lovelace"), recipient("Alan Turing")]),
    )
    job_id = created.json()["id"]

    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        first = sorted(job.certificates, key=lambda item: item.position)[0]
        first.status = CertificateStatus.succeeded.value
        first.certificate_number = "CERT-2026-AAAAAAAAAAAA"
        job.success_count = 1
        job.pending_count = 1
        db.commit()
    finally:
        db.close()

    run_queued_jobs()
    assert calls["count"] == 1
    finished = client.get(f"/api/v1/jobs/{job_id}").json()
    assert finished["progress"]["succeeded"] == 2
    assert finished["status"] == "completed"


def test_only_one_worker_can_claim_a_queued_job(client):
    created = client.post("/api/v1/jobs", json=payload([recipient("Ada Lovelace")]))
    job_id = created.json()["id"]

    db = SessionLocal()
    try:
        assert claim_queued_job(db, job_id) is True
        assert claim_queued_job(db, job_id) is False
        job = db.get(GenerationJob, job_id)
        db.refresh(job)
        assert job.status == JobStatus.processing.value
    finally:
        db.close()

    assert process_next_job() is False
