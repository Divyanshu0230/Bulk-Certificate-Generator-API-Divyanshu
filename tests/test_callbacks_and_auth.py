import httpx

from tests.conftest import payload, recipient, run_queued_jobs


def test_callback_is_sent_when_the_job_completes(client, monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["json"] = kwargs["json"]

        class Response:
            status_code = 204

        return Response()

    monkeypatch.setattr("app.services.callbacks.httpx.post", fake_post)
    created = client.post(
        "/api/v1/jobs",
        json=payload(
            [recipient("Ada Lovelace")],
            callback_url="https://example.com/hooks/certificates",
        ),
    )
    run_queued_jobs()

    assert captured["url"] == "https://example.com/hooks/certificates"
    assert captured["json"]["id"] == created.json()["id"]
    assert captured["json"]["status"] == "completed"
    assert captured["json"]["progress"]["succeeded"] == 1


def test_callback_failure_does_not_fail_the_job(client, monkeypatch):
    def fake_post(*_args, **_kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.services.callbacks.httpx.post", fake_post)
    created = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Ada Lovelace")], callback_url="https://example.com/hooks/certificates"),
    )
    run_queued_jobs()

    finished = client.get(f"/api/v1/jobs/{created.json()['id']}").json()
    assert finished["status"] == "completed"
    assert finished["progress"]["succeeded"] == 1


def test_api_key_protects_generation_but_not_verification(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "api_key", "reviewer-secret")
    body = payload([recipient("Ada Lovelace", "ada@example.com")])

    blocked = client.post("/api/v1/jobs", json=body)
    assert blocked.status_code == 401

    health = client.get("/health")
    assert health.status_code == 200

    created = client.post("/api/v1/jobs", json=body, headers={"X-API-Key": "reviewer-secret"})
    assert created.status_code == 202
    run_queued_jobs()

    hidden = client.get(f"/api/v1/jobs/{created.json()['id']}")
    assert hidden.status_code == 401

    visible = client.get(
        f"/api/v1/jobs/{created.json()['id']}",
        headers={"X-API-Key": "reviewer-secret"},
    )
    number = client.get(
        f"/api/v1/jobs/{created.json()['id']}/certificates",
        headers={"X-API-Key": "reviewer-secret"},
    ).json()["items"][0]["certificate_number"]

    assert visible.status_code == 200
    verified = client.get(f"/api/v1/verify/{number}")
    assert verified.status_code == 200
    assert verified.json()["recipient_name"] == "Ada Lovelace"
