"""FastAPI application entry point for ResolveIQ Document Intelligence & Classification Engine."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.ai.documents import DocumentExtractionError, DocumentValidationError
from backend.api.automation_routes import router as automation_router
from backend.api.disputes import router as disputes_router
from backend.api.documents import router as documents_router
from backend.api.paypal_routes import router as paypal_router
from backend.api.resolution import router as resolution_router
from backend.config import Settings, get_settings
from backend.db import Database, init_db

_initial_settings = get_settings()
log_level = getattr(logging, _initial_settings.log_level.upper(), logging.INFO)

logging.basicConfig(
    level=log_level,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("resolveiq")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db(settings.db_path)
    logger.info(
        "ResolveIQ initialized [env=%s, db=%s, upload_dir=%s]",
        settings.environment,
        settings.db_path,
        settings.upload_dir,
    )
    yield
    logger.info("ResolveIQ backend shutting down")


app = FastAPI(
    title="ResolveIQ - Document Intelligence & AI Dispute Classification API",
    description=(
        "Production-grade dispute resolution intelligence engine: multi-format document parser "
        "(PyMuPDF, python-docx, OCR), structured evidence extractor, and Gemini-powered dispute classifier."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# Request body size limiter middleware (guards against payload bomb DoS)
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            length = int(content_length)
            settings_getter = request.app.dependency_overrides.get(get_settings, get_settings)
            settings = settings_getter()
            max_bytes = settings.max_request_body_size_mb * 1024 * 1024
            if length > max_bytes:
                payload_too_large_code = getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413)
                return JSONResponse(
                    status_code=payload_too_large_code,
                    content={
                        "detail": f"Request body ({length} bytes) exceeds configured limit of {settings.max_request_body_size_mb}MB",
                        "error_type": "PayloadTooLarge",
                    },
                )
        except ValueError:
            pass
    return await call_next(request)


# CORS middleware with strict origin controls
_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.allowed_origins if _settings.allowed_origins else ["*"],
    allow_origin_regex=_settings.allowed_origin_regex if _settings.allowed_origin_regex else None,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Include routers
app.include_router(documents_router)
app.include_router(disputes_router)
app.include_router(resolution_router)
app.include_router(paypal_router)
app.include_router(automation_router)


# Custom exception handlers
@app.exception_handler(DocumentValidationError)
async def validation_error_handler(request: Request, exc: DocumentValidationError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc), "error_type": "DocumentValidationError"},
    )


@app.exception_handler(DocumentExtractionError)
async def extraction_error_handler(request: Request, exc: DocumentExtractionError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc), "error_type": "DocumentExtractionError"},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """Catch unhandled errors and return a safe generic message without leaking internals."""
    from fastapi import HTTPException
    from starlette.exceptions import HTTPException as StarletteHTTPException
    if isinstance(exc, (HTTPException, StarletteHTTPException, DocumentValidationError, DocumentExtractionError)):
        raise exc

    logger.exception("Unhandled server error processing %s: %s", request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An internal server error occurred while processing your request.",
            "error_type": "InternalServerError",
        },
    )


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health_check(settings: Settings = Depends(get_settings)):
    """Comprehensive production health-check endpoint. Never exposes API secrets."""
    db_connected = False
    try:
        from backend.db import _get_connection
        with _get_connection(settings.db_path) as conn:
            conn.execute("SELECT 1;").fetchone()
            db_connected = True
    except Exception as exc:
        logger.warning("Health check database probe failed: %s", exc)

    storage_writeable = False
    try:
        p = Path(settings.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        probe_file = p / ".health_probe"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink(missing_ok=True)
        storage_writeable = True
    except Exception as exc:
        logger.warning("Health check storage probe failed: %s", exc)

    status_str = "healthy" if (db_connected and storage_writeable) else "degraded"

    return {
        "status": status_str,
        "service": "ResolveIQ Intelligence Engine",
        "version": "2.0.0",
        "environment": settings.environment,
        "database_connected": db_connected,
        "storage_writeable": storage_writeable,
        "gemini_configured": bool(settings.gemini_api_key),
        "gemini_model": settings.gemini_model,
        "paypal_configured": bool(settings.paypal_client_id and settings.paypal_client_secret),
        "zapier_configured": bool(settings.zapier_webhook_url),
        "max_upload_size_mb": settings.max_upload_size_mb,
    }


# Mount frontend static files if built
frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
