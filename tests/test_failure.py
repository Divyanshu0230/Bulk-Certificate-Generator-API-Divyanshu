from app.services.pdf import render_certificate
from tests.conftest import payload, recipient, run_queued_jobs


def test_one_certificate_failure_does_not_stop_the_rest(client, monkeypatch):
    real_render = render_certificate

    def flaky(**kwargs):
        if kwargs["recipient_name"] == "Broken Record":
            raise RuntimeError("disk full simulated")
        real_render(**kwargs)

    monkeypatch.setattr("app.services.jobs.render_certificate", flaky)
    created = client.post(
        "/api/v1/jobs",
        json=payload(
            [
                recipient("Ada Lovelace", "ada@example.com"),
                recipient("Broken Record", "broken@example.com"),
                recipient("Grace Hopper", "grace@example.com"),
            ]
        ),
    )
    job_id = created.json()["id"]
    run_queued_jobs()

    finished = client.get(f"/api/v1/jobs/{job_id}").json()
    assert finished["status"] == "completed_with_errors"
    assert finished["progress"]["succeeded"] == 2
    assert finished["progress"]["failed"] == 1

    certificates = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"]
    by_name = {item["recipient_name"]: item for item in certificates}
    assert by_name["Ada Lovelace"]["status"] == "succeeded"
    assert by_name["Grace Hopper"]["status"] == "succeeded"
    failed = by_name["Broken Record"]
    assert failed["status"] == "failed"
    assert failed["failure_stage"] == "generation"
    assert failed["error_message"] == "Unexpected error while generating the certificate"
    assert "disk full" not in failed["error_message"]
    assert failed["download_url"] is None

    ada = client.get(f"/api/v1/certificates/{by_name['Ada Lovelace']['id']}/download")
    grace = client.get(f"/api/v1/certificates/{by_name['Grace Hopper']['id']}/download")
    broken = client.get(f"/api/v1/certificates/{failed['id']}/download")
    assert ada.status_code == 200
    assert grace.status_code == 200
    assert broken.status_code == 409


def test_unsupported_character_fails_one_recipient_only(client):
    created = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Ada Lovelace"), recipient("王明")]),
    )
    job_id = created.json()["id"]
    run_queued_jobs()

    finished = client.get(f"/api/v1/jobs/{job_id}").json()
    assert finished["status"] == "completed_with_errors"
    certificates = client.get(f"/api/v1/jobs/{job_id}/certificates").json()["items"]
    by_name = {item["recipient_name"]: item for item in certificates}
    assert by_name["Ada Lovelace"]["status"] == "succeeded"
    assert by_name["王明"]["status"] == "failed"
    assert by_name["王明"]["failure_stage"] == "generation"
    assert "cannot draw" in by_name["王明"]["error_message"]
