from datetime import datetime, timezone

from app.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def public_url(path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return f"{get_settings().public_base_url}{path}"
