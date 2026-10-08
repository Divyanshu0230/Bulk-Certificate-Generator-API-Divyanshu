from tests.conftest import payload, recipient, run_queued_jobs


def test_create_generation_job(client):
    response = client.post(
        "/api/v1/jobs",
        json=payload(
            [
                recipient("Ada Lovelace", "ada@example.com", "EMP-1", "With distinction"),
                recipient("Alan Turing", "alan@example.com", "EMP-2"),
            ]
        ),
    )

    assert response.status_code == 202
    body = response.json()
    assert response.headers["location"] == f"/api/v1/jobs/{body['id']}"
    assert body["status"] == "queued"
    assert body["event"]["title"] == "Advanced Python Workshop"
    assert body["event"]["issuer"] == "Northwind Academy"
    assert body["progress"] == {
        "total": 2,
        "pending": 2,
        "succeeded": 0,
        "failed": 0,
        "percent_complete": 0,
    }
    assert body["validation_issues"] == []
    assert body["links"]["self"].endswith(f"/api/v1/jobs/{body['id']}")

    listed = client.get("/api/v1/jobs")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    run_queued_jobs()
    finished = client.get(f"/api/v1/jobs/{body['id']}")
    assert finished.json()["status"] == "completed"
    assert finished.json()["progress"]["succeeded"] == 2
    assert finished.json()["started_at"] is not None
    assert finished.json()["completed_at"] is not None


def test_browser_home_page_and_json_root(client):
    page = client.get("/", headers={"Accept": "text/html"})
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Generate certificates" in page.text

    data = client.get("/", headers={"Accept": "application/json"})
    assert data.json()["docs"] == "/docs"


def test_health_endpoints(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ok"}
