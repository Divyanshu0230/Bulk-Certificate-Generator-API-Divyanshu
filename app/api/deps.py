import secrets
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import SessionLocal
from app.exceptions import Unauthorized


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    """Require ``X-API-Key`` only when ``API_KEY`` is configured.

    Verification and health stay public so a printed QR code can be checked
    without the organizer's credential.
    """

    expected = get_settings().api_key
    if not expected:
        return
    if x_api_key is None or not secrets.compare_digest(x_api_key, expected):
        raise Unauthorized()


DbSession = Annotated[Session, Depends(get_db)]
