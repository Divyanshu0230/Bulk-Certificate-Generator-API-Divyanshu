import os
import shutil
import tempfile
from pathlib import Path

_ROOT = Path(tempfile.mkdtemp(prefix="certgen-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_ROOT / 'test.db'}"
os.environ["STORAGE_DIR"] = str(_ROOT / "storage")
os.environ["WORKER_ENABLED"] = "false"
os.environ["PUBLIC_BASE_URL"] = "http://127.0.0.1:8000"
os.environ["API_KEY"] = ""
os.environ["MAX_RECIPIENTS_PER_JOB"] = "500"

import pytest
from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app
from app.services.worker import process_next_job

EVENT = {
    "title": "Advanced Python Workshop",
    "issuer": "Northwind Academy",
    "issue_date": "2026-10-08",
    "description": "has successfully completed",
    "signatory_name": "Dr. Meera Shah",
    "signatory_title": "Program Director",
}


def recipient(name, email=None, external_id=None, detail=None):
    body = {"name": name}
    if email is not None:
        body["email"] = email
    if external_id is not None:
        body["external_id"] = external_id
    if detail is not None:
        body["detail"] = detail
    return body


def payload(recipients, **extra):
    body = {"event": dict(EVENT), "recipients": list(recipients)}
    body.update(extra)
    return body


def run_queued_jobs():
    for _ in range(20):
        if not process_next_job():
            return
    raise AssertionError("queued jobs did not finish")


@pytest.fixture(autouse=True)
def _reset_state():
    storage = Path(os.environ["STORAGE_DIR"])
    if storage.exists():
        shutil.rmtree(storage)
    storage.mkdir(parents=True, exist_ok=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
