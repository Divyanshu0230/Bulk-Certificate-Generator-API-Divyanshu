from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.models import CertificateStatus, FailureStage, JobStatus


def _collapse(value: object) -> object:
    if not isinstance(value, str):
        return value
    collapsed = " ".join(value.split())
    return collapsed or None


class EventIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=3, max_length=200, description="Course or event name printed on the certificate.")
    issuer: str = Field(min_length=2, max_length=200, description="Organization awarding the certificate.")
    issue_date: date = Field(description="Date printed on the certificate.")
    description: str | None = Field(
        default=None,
        max_length=300,
        description="Line under the recipient name. Defaults to 'has successfully completed'.",
    )
    signatory_name: str | None = Field(default=None, max_length=120)
    signatory_title: str | None = Field(default=None, max_length=120)

    @field_validator("title", "issuer", "description", "signatory_name", "signatory_title", mode="before")
    @classmethod
    def collapse_whitespace(cls, value: object) -> object:
        return _collapse(value)

    @field_validator("issue_date")
    @classmethod
    def date_in_supported_range(cls, value: date) -> date:
        earliest = date(1990, 1, 1)
        latest = datetime.now(timezone.utc).date() + timedelta(days=365 * 5 + 1)
        if value < earliest or value > latest:
            raise ValueError("must be between 1990 and five years from today")
        return value


class RecipientIn(BaseModel):
    """One person in a bulk request.

    Structural limits live here. Content rules (a real name, a valid email,
    a unique external id) are applied per row so one bad recipient does not
    reject the whole batch.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    external_id: str | None = Field(
        default=None,
        max_length=80,
        description="Caller reference, unique within this request. Stored for the organizer, not printed.",
    )
    detail: str | None = Field(
        default=None,
        max_length=200,
        description="Optional line printed only on this recipient's certificate, such as a grade or track.",
    )

    @field_validator("name", "email", "external_id", "detail", mode="before")
    @classmethod
    def collapse_whitespace(cls, value: object) -> object:
        return _collapse(value)


class GenerateRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "event": {
                    "title": "Advanced Python Workshop",
                    "issuer": "Northwind Academy",
                    "issue_date": "2026-10-08",
                    "description": "has successfully completed",
                    "signatory_name": "Dr. Meera Shah",
                    "signatory_title": "Program Director",
                },
                "recipients": [
                    {
                        "name": "Ada Lovelace",
                        "email": "ada@example.com",
                        "external_id": "EMP-1",
                        "detail": "With distinction",
                    },
                    {
                        "name": "Alan Turing",
                        "email": "alan@example.com",
                        "external_id": "EMP-2",
                    },
                ],
            }
        },
    )

    event: EventIn
    recipients: list[RecipientIn] = Field(min_length=1)
    callback_url: HttpUrl | None = Field(
        default=None,
        description="Optional URL that receives the job summary when processing finishes.",
    )

    @field_validator("callback_url", mode="before")
    @classmethod
    def blank_callback_is_absent(cls, value: object) -> object:
        if value == "":
            return None
        return value


class EventOut(BaseModel):
    title: str
    issuer: str
    issue_date: date
    description: str
    signatory_name: str | None = None
    signatory_title: str | None = None


class Progress(BaseModel):
    total: int
    pending: int
    succeeded: int
    failed: int
    percent_complete: int


class JobLinks(BaseModel):
    self: str
    certificates: str
    archive: str
    report: str


class JobRead(BaseModel):
    id: str
    status: JobStatus
    event: EventOut
    progress: Progress
    callback_url: str | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    links: JobLinks


class RecipientIssue(BaseModel):
    position: int
    field: str
    message: str


class JobCreated(JobRead):
    validation_issues: list[RecipientIssue] = []


class JobList(BaseModel):
    items: list[JobRead]
    total: int
    limit: int
    offset: int


class CertificateRead(BaseModel):
    id: str
    job_id: str
    position: int
    recipient_name: str
    recipient_email: str | None = None
    external_id: str | None = None
    detail: str | None = None
    status: CertificateStatus
    failure_stage: FailureStage | None = None
    error_message: str | None = None
    certificate_number: str | None = None
    created_at: datetime
    generated_at: datetime | None = None
    download_url: str | None = None
    verify_url: str | None = None


class CertificateList(BaseModel):
    items: list[CertificateRead]
    total: int
    limit: int
    offset: int


class Verification(BaseModel):
    valid: bool = True
    certificate_number: str
    recipient_name: str
    event_title: str
    issuer: str
    issue_date: date
    description: str
    detail: str | None = None
