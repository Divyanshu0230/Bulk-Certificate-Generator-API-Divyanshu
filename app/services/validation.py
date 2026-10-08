import re
import unicodedata
from dataclasses import dataclass, field

from app.schemas import RecipientIn

_EMAIL = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_EXTERNAL_ID = re.compile(r"^[A-Za-z0-9._:\-]{1,64}$")


@dataclass(frozen=True)
class FieldIssue:
    position: int
    field: str
    message: str


@dataclass
class RecipientDraft:
    position: int
    name: str
    email: str | None
    external_id: str | None
    detail: str | None
    issues: list[FieldIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.issues


def _has_letter(value: str) -> bool:
    return any(unicodedata.category(character).startswith("L") for character in value)


def _has_control_character(value: str) -> bool:
    return any(unicodedata.category(character) == "Cc" for character in value)


def validate_recipients(recipients: list[RecipientIn]) -> list[RecipientDraft]:
    """Validate each recipient independently.

    The first valid use of an external id wins. Later duplicates are recorded
    as failures and do not remove the earlier row.
    """

    drafts: list[RecipientDraft] = []
    seen_external_ids: set[str] = set()

    for position, recipient in enumerate(recipients):
        issues: list[FieldIssue] = []
        name = recipient.name or ""

        if not name:
            issues.append(FieldIssue(position, "name", "Name is required"))
        elif not 2 <= len(name) <= 120:
            issues.append(FieldIssue(position, "name", "Name must be between 2 and 120 characters"))
        elif not _has_letter(name):
            issues.append(FieldIssue(position, "name", "Name must contain at least one letter"))
        elif _has_control_character(name):
            issues.append(FieldIssue(position, "name", "Name contains invalid characters"))

        email = recipient.email
        if email is not None and (len(email) > 254 or _EMAIL.fullmatch(email) is None):
            issues.append(FieldIssue(position, "email", "Email is not valid"))

        external_id = recipient.external_id
        if external_id is not None:
            if _EXTERNAL_ID.fullmatch(external_id) is None:
                issues.append(
                    FieldIssue(
                        position,
                        "external_id",
                        "External id must be 1-64 characters and use only letters, numbers, and . _ : -",
                    )
                )
            elif external_id in seen_external_ids:
                issues.append(
                    FieldIssue(position, "external_id", "External id is duplicated in this request")
                )
            else:
                seen_external_ids.add(external_id)

        detail = recipient.detail
        if detail is not None and not 1 <= len(detail) <= 120:
            issues.append(FieldIssue(position, "detail", "Detail must be between 1 and 120 characters"))

        drafts.append(
            RecipientDraft(
                position=position,
                name=name or "(missing name)",
                email=email,
                external_id=external_id,
                detail=detail,
                issues=issues,
            )
        )

    return drafts
