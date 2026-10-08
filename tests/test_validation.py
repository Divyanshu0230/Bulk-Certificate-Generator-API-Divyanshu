from tests.conftest import payload, recipient, run_queued_jobs


def test_empty_recipient_list_is_rejected(client):
    response = client.post("/api/v1/jobs", json=payload([]))

    assert response.status_code == 422
    assert response.json()["detail"] == "Request validation failed"
    assert client.get("/api/v1/jobs").json()["total"] == 0


def test_missing_event_title_is_rejected(client):
    body = payload([recipient("Ada Lovelace")])
    del body["event"]["title"]

    response = client.post("/api/v1/jobs", json=body)

    assert response.status_code == 422
    assert any(error["field"] == "event.title" for error in response.json()["errors"])


def test_issue_date_outside_supported_range_is_rejected(client):
    body = payload([recipient("Ada Lovelace")])
    body["event"]["issue_date"] = "1800-01-01"

    response = client.post("/api/v1/jobs", json=body)

    assert response.status_code == 422


def test_unknown_recipient_field_is_rejected(client):
    response = client.post(
        "/api/v1/jobs",
        json=payload([{"name": "Ada Lovelace", "full_name": "Ada"}]),
    )

    assert response.status_code == 422
    assert client.get("/api/v1/jobs").json()["total"] == 0


def test_invalid_recipient_is_recorded_and_valid_recipient_still_generates(client):
    response = client.post(
        "/api/v1/jobs",
        json=payload(
            [
                recipient("Ada Lovelace", "ada@example.com", "EMP-1"),
                recipient("No Email", "not-an-email", "EMP-2"),
                recipient("12345", external_id="EMP-3"),
            ]
        ),
    )

    assert response.status_code == 202
    body = response.json()
    assert body["progress"]["pending"] == 1
    assert body["progress"]["failed"] == 2
    fields = {(issue["position"], issue["field"]) for issue in body["validation_issues"]}
    assert (1, "email") in fields
    assert (2, "name") in fields

    rows = client.get(f"/api/v1/jobs/{body['id']}/certificates?status=failed").json()
    assert rows["total"] == 2
    assert rows["items"][0]["failure_stage"] == "validation"
    assert rows["items"][0]["status"] == "failed"

    run_queued_jobs()
    finished = client.get(f"/api/v1/jobs/{body['id']}").json()
    assert finished["status"] == "completed_with_errors"
    assert finished["progress"]["succeeded"] == 1
    assert finished["progress"]["failed"] == 2
    assert finished["progress"]["percent_complete"] == 100


def test_duplicate_external_id_fails_only_the_later_row(client):
    response = client.post(
        "/api/v1/jobs",
        json=payload(
            [
                recipient("Ada Lovelace", external_id="EMP-1"),
                recipient("Augusta Ada", external_id="EMP-1"),
            ]
        ),
    )

    assert response.status_code == 202
    issues = response.json()["validation_issues"]
    assert len(issues) == 1
    assert issues[0]["position"] == 1
    assert issues[0]["field"] == "external_id"
    assert issues[0]["message"] == "External id is duplicated in this request"

    run_queued_jobs()
    certificates = client.get(f"/api/v1/jobs/{response.json()['id']}/certificates").json()["items"]
    assert certificates[0]["status"] == "succeeded"
    assert certificates[1]["status"] == "failed"


def test_request_with_no_valid_recipients_does_not_create_a_job(client):
    response = client.post(
        "/api/v1/jobs",
        json=payload([recipient("x"), recipient("12345", email="bad")]),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "No valid recipients to process"
    assert response.json()["errors"]
    assert client.get("/api/v1/jobs").json()["total"] == 0


def test_too_many_recipients_is_rejected(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "max_recipients_per_job", 1)
    response = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Ada Lovelace"), recipient("Alan Turing")]),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "A job can include at most 1 recipient"
    assert client.get("/api/v1/jobs").json()["total"] == 0
