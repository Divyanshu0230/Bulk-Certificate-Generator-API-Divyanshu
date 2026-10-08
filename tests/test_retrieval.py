import io
import zipfile

from tests.conftest import payload, recipient, run_queued_jobs


def _create_finished_job(client, recipients):
    created = client.post("/api/v1/jobs", json=payload(recipients))
    assert created.status_code == 202
    run_queued_jobs()
    return created.json()["id"]


def test_download_generated_certificate_and_reject_missing_ones(client):
    job_id = _create_finished_job(client, [recipient("Ada Lovelace", "ada@example.com")])
    certificate = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"][0]

    missing = client.get("/api/v1/certificates/does-not-exist")
    assert missing.status_code == 404

    metadata = client.get(f"/api/v1/certificates/{certificate['id']}")
    assert metadata.status_code == 200
    assert metadata.json()["recipient_name"] == "Ada Lovelace"
    assert "file_path" not in metadata.json()

    download = client.get(f"/api/v1/certificates/{certificate['id']}/download")
    assert download.status_code == 200
    assert download.content.startswith(b"%PDF")


def test_certificate_can_be_previewed_inline(client):
    job_id = _create_finished_job(client, [recipient("Ada Lovelace")])
    certificate = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"][0]

    preview = client.get(f"/api/v1/certificates/{certificate['id']}/download?inline=true")
    assert preview.status_code == 200
    assert preview.content.startswith(b"%PDF")
    assert "inline" in preview.headers["content-disposition"]

    sample = client.get("/sample-certificate.pdf")
    assert sample.status_code == 200
    assert sample.content.startswith(b"%PDF")

    image = client.get(f"/api/v1/certificates/{certificate['id']}/preview.png")
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.content.startswith(b"\x89PNG")


def test_download_is_rejected_before_generation(client):
    created = client.post("/api/v1/jobs", json=payload([recipient("Ada Lovelace")]))
    certificate = client.get(f"/api/v1/jobs/{created.json()['id']}/certificates").json()["items"][0]

    download = client.get(f"/api/v1/certificates/{certificate['id']}/download")
    archive = client.get(f"/api/v1/jobs/{created.json()['id']}/archive")
    assert download.status_code == 409
    assert archive.status_code == 409


def test_zip_contains_only_successful_certificates(client):
    job_id = _create_finished_job(
        client,
        [
            recipient("Ada Lovelace"),
            recipient("x"),
            recipient("Grace Hopper"),
        ],
    )
    archive = client.get(f"/api/v1/jobs/{job_id}/archive")
    assert archive.status_code == 200
    assert archive.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(archive.content)) as bundle:
        names = bundle.namelist()
    assert len(names) == 2
    assert any(name.startswith("Ada-Lovelace-") for name in names)
    assert any(name.startswith("Grace-Hopper-") for name in names)
    assert all(name.endswith(".pdf") for name in names)


def test_csv_report_lists_successes_and_failures(client):
    job_id = _create_finished_job(
        client,
        [
            recipient("=HYPERLINK Ada", "ada@example.com", "EMP-1"),
            recipient("x"),
        ],
    )
    report = client.get(f"/api/v1/jobs/{job_id}/report")
    assert report.status_code == 200
    text = report.content.decode("utf-8-sig")
    assert "recipient_name" in text.splitlines()[0]
    assert "'=HYPERLINK Ada" in text
    assert "ada@example.com" in text
    assert "Name must be between 2 and 120 characters" in text
    assert "succeeded" in text
    assert "validation" in text
