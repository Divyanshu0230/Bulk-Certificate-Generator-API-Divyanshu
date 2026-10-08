from tests.conftest import payload, recipient, run_queued_jobs


def test_verify_public_certificate_hides_email(client):
    created = client.post(
        "/api/v1/jobs",
        json=payload([recipient("Ada Lovelace", "ada@example.com", "EMP-77", "With distinction")]),
    )
    run_queued_jobs()
    certificate = client.get(f"/api/v1/jobs/{created.json()['id']}/certificates").json()["items"][0]
    number = certificate["certificate_number"]

    verified = client.get(f"/api/v1/verify/{number}")
    assert verified.status_code == 200
    body = verified.json()
    assert body["valid"] is True
    assert body["recipient_name"] == "Ada Lovelace"
    assert body["event_title"] == "Advanced Python Workshop"
    assert body["issuer"] == "Northwind Academy"
    assert body["detail"] == "With distinction"
    assert "email" not in body
    assert "ada@example.com" not in verified.text
    assert "EMP-77" not in verified.text

    page = client.get(f"/api/v1/verify/{number}", headers={"Accept": "text/html"})
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Valid certificate" in page.text
    assert "Ada Lovelace" in page.text
    assert "ada@example.com" not in page.text


def test_unknown_certificate_number_is_not_found(client):
    missing = client.get("/api/v1/verify/CERT-2026-0123456789AB")
    assert missing.status_code == 404
    assert missing.json()["detail"] == "Certificate not found"

    page = client.get(
        "/api/v1/verify/CERT-2026-0123456789AB",
        headers={"Accept": "text/html"},
    )
    assert page.status_code == 404
    assert "not valid" in page.text
