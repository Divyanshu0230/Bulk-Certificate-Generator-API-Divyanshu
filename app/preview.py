"""Write one sample certificate without starting the API.

Run from the project root:

    python -m app.preview
"""

from datetime import date
from pathlib import Path

from app.services.pdf import render_certificate


def main() -> None:
    destination = Path("examples") / "sample-certificate.pdf"
    render_certificate(
        destination=destination,
        recipient_name="Ada Lovelace",
        event_title="Advanced Python Workshop",
        issuer="Northwind Academy",
        issue_date=date(2026, 10, 8),
        description="has successfully completed",
        detail="With distinction",
        certificate_number="CERT-2026-4F8C1A9B2E07",
        verify_url="http://127.0.0.1:8000/api/v1/verify/CERT-2026-4F8C1A9B2E07",
        signatory_name="Dr. Meera Shah",
        signatory_title="Program Director",
    )
    print(destination.resolve())


if __name__ == "__main__":
    main()
