from tests.conftest import payload, recipient, run_queued_jobs


def test_idempotency_key_replays_the_same_job(client):
    body = payload([recipient("Ada Lovelace", "ada@example.com")])
    headers = {"Idempotency-Key": "batch-2026-10-08-ada"}

    first = client.post("/api/v1/jobs", json=body, headers=headers)
    second = client.post("/api/v1/jobs", json=body, headers=headers)

    assert first.status_code == 202
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert client.get("/api/v1/jobs").json()["total"] == 1

    spaced = payload([recipient("  Ada   Lovelace  ", "ada@example.com")])
    replay = client.post("/api/v1/jobs", json=spaced, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]

    run_queued_jobs()
    after = client.post("/api/v1/jobs", json=body, headers=headers)
    assert after.status_code == 200
    assert after.json()["status"] == "completed"
    assert client.get("/api/v1/jobs").json()["total"] == 1


def test_idempotency_key_conflicts_when_the_body_changes(client):
    headers = {"Idempotency-Key": "batch-locked"}
    first = client.post("/api/v1/jobs", json=payload([recipient("Ada Lovelace")]), headers=headers)
    assert first.status_code == 202

    conflict = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Alan Turing")]),
        headers=headers,
    )
    assert conflict.status_code == 409
    assert client.get("/api/v1/jobs").json()["total"] == 1


def test_malformed_idempotency_key_is_rejected(client):
    response = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Ada Lovelace")]),
        headers={"Idempotency-Key": "has spaces"},
    )
    assert response.status_code == 400
    assert client.get("/api/v1/jobs").json()["total"] == 0
