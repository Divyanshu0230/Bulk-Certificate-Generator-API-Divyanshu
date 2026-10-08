import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response

from app.api.routes import certificates, health, jobs, verify
from app.config import get_settings
from app.database import init_database
from app.exceptions import AppError
from app.services.preview_image import render_pdf_png
from app.services.worker import JobWorker

def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    init_database()
    settings = get_settings()
    worker = None
    if settings.worker_enabled:
        worker = JobWorker(settings.worker_poll_interval_seconds)
        worker.start()
        app.state.worker = worker
    yield
    if worker is not None:
        worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        summary="Generate certificates for many recipients in one request.",
        description=(
            "Submit one job with the shared event details and a list of recipients. "
            "The API validates each recipient, generates a PDF for every valid row, "
            "and keeps going when a single certificate fails. Poll the job for progress, "
            "then download individual PDFs, a zip, or a CSV report."
        ),
        lifespan=lifespan,
        openapi_tags=[
            {"name": "jobs", "description": "Submit a batch and track its progress."},
            {"name": "certificates", "description": "Inspect and download generated certificates."},
            {
                "name": "verification",
                "description": "Public check that a certificate number was issued. No API key required.",
            },
            {"name": "health", "description": "Process and database health."},
        ],
    )

    origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(jobs.router, prefix="/api/v1")
    app.include_router(certificates.router, prefix="/api/v1")
    app.include_router(verify.router, prefix="/api/v1")

    @app.get("/sample-certificate.pdf", include_in_schema=False)
    def sample_certificate() -> FileResponse:
        return FileResponse(
            _sample_pdf(),
            media_type="application/pdf",
            filename="sample-certificate.pdf",
            content_disposition_type="inline",
        )

    @app.get("/sample-certificate.png", include_in_schema=False)
    def sample_certificate_image() -> Response:
        return Response(content=render_pdf_png(_sample_pdf()), media_type="image/png")

    @app.get("/", include_in_schema=False)
    def root(request: Request):
        if _wants_html(request):
            page = Path(__file__).resolve().parent / "static" / "index.html"
            return HTMLResponse(page.read_text(encoding="utf-8"))
        return {
            "name": settings.app_name,
            "docs": "/docs",
            "health": "/health",
            "jobs": "/api/v1/jobs",
        }

    @app.exception_handler(AppError)
    def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        body: dict = {"detail": exc.detail}
        if exc.errors:
            body["errors"] = exc.errors
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    def handle_request_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = []
        for error in exc.errors():
            location = [str(part) for part in error.get("loc", []) if part != "body"]
            errors.append({"field": ".".join(location) or "body", "message": error.get("msg", "Invalid value")})
        return JSONResponse(
            status_code=422,
            content={"detail": "Request validation failed", "errors": errors},
        )

    return app


def _sample_pdf() -> Path:
    return Path(__file__).resolve().parents[1] / "examples" / "sample-certificate.pdf"


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    for part in accept.split(","):
        media = part.split(";", 1)[0].strip().lower()
        if media == "application/json":
            return False
        if media == "text/html":
            return True
    return False


app = create_app()
