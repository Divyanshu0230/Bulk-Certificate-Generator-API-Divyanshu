class AppError(Exception):
    """Domain error with a status code safe to show to API clients."""

    status_code = 400
    detail = "Request failed"

    def __init__(self, detail: str | None = None, errors: list | None = None):
        if detail is not None:
            self.detail = detail
        self.errors = errors
        super().__init__(self.detail)


class Unauthorized(AppError):
    status_code = 401
    detail = "Invalid or missing API key"


class TooManyRecipients(AppError):
    status_code = 422

    def __init__(self, limit: int):
        noun = "recipient" if limit == 1 else "recipients"
        super().__init__(detail=f"A job can include at most {limit} {noun}")


class NoValidRecipients(AppError):
    status_code = 422
    detail = "No valid recipients to process"


class InvalidIdempotencyKey(AppError):
    status_code = 400
    detail = (
        "Idempotency-Key must be 1-200 characters and use only "
        "letters, numbers, and . _ : -"
    )


class IdempotencyConflict(AppError):
    status_code = 409
    detail = "This Idempotency-Key was already used with a different request body"


class JobNotFound(AppError):
    status_code = 404
    detail = "Job not found"


class CertificateNotFound(AppError):
    status_code = 404
    detail = "Certificate not found"


class CertificateFileMissing(AppError):
    status_code = 404
    detail = "The certificate file is no longer available"


class CertificateNotReady(AppError):
    status_code = 409

    def __init__(self, status: str):
        super().__init__(
            detail=f"This certificate is not available for download (status: {status})"
        )


class ArchiveNotReady(AppError):
    status_code = 409
    detail = "This job has no generated certificates to download yet"


class CertificateRenderError(AppError):
    """A generation problem whose message is safe to store on the certificate."""

    status_code = 500
    detail = "Certificate rendering failed"
