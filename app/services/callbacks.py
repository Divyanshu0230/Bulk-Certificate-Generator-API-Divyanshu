import logging

import httpx

from app.models import GenerationJob
from app.serializers import job_to_read

logger = logging.getLogger(__name__)


def deliver_callback(job: GenerationJob) -> None:
    """Notify the caller that a job reached a terminal status.

    Delivery problems are logged and do not change the job. The certificate
    files are already committed, and the client can still poll for them.
    """

    if not job.callback_url:
        return
    payload = job_to_read(job).model_dump(mode="json")
    try:
        response = httpx.post(
            job.callback_url,
            json=payload,
            timeout=5.0,
            follow_redirects=False,
            headers={"User-Agent": "BulkCertificateGenerator/1.0"},
        )
        logger.info("Callback for job %s returned HTTP %s", job.id, response.status_code)
    except httpx.HTTPError:
        logger.warning("Callback for job %s could not be delivered", job.id, exc_info=True)
