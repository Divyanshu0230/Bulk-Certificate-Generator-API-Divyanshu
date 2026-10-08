import io

from pypdf import PdfReader

from tests.conftest import payload, recipient, run_queued_jobs


def _pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def test_certificate_pdf_contains_recipient_details(client):
    created = client.post(
        "/api/v1/jobs",
        json=payload(
            [
                recipient("José Álvarez", "jose@example.com", "EMP-9", "With distinction"),
            ]
        ),
    )
    job_id = created.json()["id"]
    run_queued_jobs()

    certificates = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"]
    assert len(certificates) == 1
    certificate = certificates[0]
    assert certificate["status"] == "succeeded"
    assert certificate["certificate_number"].startswith("CERT-2026-")
    assert certificate["recipient_email"] == "jose@example.com"

    download = client.get(certificate["download_url"].removeprefix("http://127.0.0.1:8000"))
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"
    assert download.content.startswith(b"%PDF")
    assert certificate["certificate_number"] in download.headers["content-disposition"]

    text = _pdf_text(download.content)
    assert "José Álvarez" in text
    assert "Advanced Python Workshop" in text
    assert "NORTHWIND ACADEMY" in text
    assert "With distinction" in text
    assert "Dr. Meera Shah" in text
    assert "8 October 2026" in text
    assert certificate["certificate_number"] in text
    assert "jose@example.com" not in text


def test_long_recipient_name_is_still_rendered(client):
    name = "Alexandria Catherine Montgomery-Wallace"
    created = client.post("/api/v1/jobs", json=payload([recipient(name)]))
    run_queued_jobs()
    certificate = client.get(f"/api/v1/jobs/{created.json()['id']}/certificates").json()["items"][0]
    download = client.get(f"/api/v1/certificates/{certificate['id']}/download")
    text = _pdf_text(download.content)
    assert "Alexandria" in text
    assert "Montgomery-Wallace" in text
