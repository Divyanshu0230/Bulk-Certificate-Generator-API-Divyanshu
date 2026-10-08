import logging
import threading

from app.database import SessionLocal
from app.services.jobs import claim_next_job_id, process_job, requeue_interrupted_jobs

logger = logging.getLogger(__name__)


def process_next_job() -> bool:
    """Claim and finish one queued job. Returns False when the queue is empty."""

    db = SessionLocal()
    try:
        job_id = claim_next_job_id(db)
        if job_id is None:
            return False
        return process_job(db, job_id)
    except Exception:
        logger.exception("Certificate worker failed while claiming a job")
        db.rollback()
        return False
    finally:
        db.close()


class JobWorker:
    """In-process worker.

    The HTTP request only records the job. This thread does the PDF work so a
    large batch does not hold the connection open. ``process_job`` is separate
    from the thread, which is what the tests call and what a future external
    queue worker would call as well.
    """

    def __init__(self, poll_interval_seconds: float):
        self.poll_interval_seconds = poll_interval_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._recover()
        self._thread = threading.Thread(
            target=self._run,
            name="certificate-worker",
            daemon=True,
        )
        self._thread.start()
        logger.info("Certificate worker started")

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        logger.info("Certificate worker stopped")

    def _recover(self) -> None:
        db = SessionLocal()
        try:
            recovered = requeue_interrupted_jobs(db)
            if recovered:
                logger.warning("Requeued %s interrupted job(s)", recovered)
        finally:
            db.close()

    def _run(self) -> None:
        while not self._stop.is_set():
            worked = False
            try:
                worked = process_next_job()
            except Exception:
                logger.exception("Certificate worker tick failed")
            if self._stop.wait(0 if worked else self.poll_interval_seconds):
                return
