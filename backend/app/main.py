"""Application entry point."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .core.config import settings
from .core.db import SessionLocal, engine
from .core.errors import ServiceError
from .core.i18n import request_lang, translate
from .routers import attendance, auth, portal, public_exam, public_survey, reports, schedule, surveys, trainees
from .services.media import media_root

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("attendance")


def warm_pool(count: int = 6) -> None:
    """Open a few connections up front so the first burst of scans does not pay the MySQL handshake cost."""
    conns = []
    try:
        for _ in range(count):
            conn = engine.connect()
            conn.execute(text("SELECT 1"))
            conns.append(conn)
    finally:
        for conn in conns:
            conn.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    media_root()
    try:
        warm_pool(min(6, settings.db_pool_size))
        log.info("Database connection OK (pool_size=%s, max_overflow=%s)", settings.db_pool_size, settings.db_max_overflow)
    except Exception:  # keep serving /health so the failure is visible, not a crash loop
        log.exception("Database is not reachable at startup")
    yield
    engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if settings.is_production else "/api/docs",
    redoc_url=None,
    openapi_url=None if settings.is_production else "/api/openapi.json",
)

app.add_middleware(GZipMiddleware, minimum_size=1024)
if settings.cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; connect-src 'self'; media-src 'self' blob:; worker-src 'self' blob:; "
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("Unhandled error rid=%s %s %s", request_id, request.method, request.url.path)
        response = JSONResponse(
            {"detail": translate("حدث خطأ من جانبنا. من فضلك حاول مرة أخرى.", request_lang(request)), "code": "internal_error", "request_id": request_id},
            status_code=500,
        )
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["Server-Timing"] = f"app;dur={elapsed_ms:.1f}"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=()")
    response.headers.setdefault("Content-Security-Policy", CSP)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    if elapsed_ms > 1000 or response.status_code >= 500:
        log.warning("rid=%s %s %s -> %s in %.0fms", request_id, request.method, request.url.path, response.status_code, elapsed_ms)
    return response


@app.exception_handler(ServiceError)
async def service_error_handler(request: Request, exc: ServiceError):
    return JSONResponse(
        {"detail": translate(exc.message, request_lang(request)), "code": exc.code},
        status_code=exc.status_code,
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    messages = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"] if p not in ("body", "query", "path"))
        messages.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    lang = request_lang(request)
    detail = "; ".join(messages) if messages else translate("طلب غير صالح", lang)
    return JSONResponse({"detail": detail, "code": "validation_error"}, status_code=422)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    if isinstance(detail, str):
        detail = translate(detail, request_lang(request))
    return JSONResponse({"detail": detail, "code": "http_error"}, status_code=exc.status_code, headers=exc.headers)


# ------------------------------------------------------------------------- routes
api_prefix = "/api"
for module in (auth, trainees, schedule, attendance, surveys, portal, public_survey, public_exam, reports):
    app.include_router(module.router, prefix=api_prefix)


@app.get("/health", include_in_schema=False)
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/health/ready", include_in_schema=False)
def ready():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "up"}
    except Exception:
        log.exception("readiness check failed")
        return JSONResponse({"status": "degraded", "database": "down"}, status_code=503)


@app.get("/api/public/config")
def public_config() -> dict:
    from .services import settings as settings_service

    with SessionLocal() as db:
        cfg = settings_service.get_all(db)
    return {"app_name": settings.app_name, "program_name": cfg["program_name"], "timezone": settings.timezone}


@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(path: str, request: Request):
    return JSONResponse({"detail": translate("غير موجود", request_lang(request)), "code": "not_found"}, status_code=404)


app.mount("/media", StaticFiles(directory=str(media_root())), name="media")

# Serve the built React app when present (single-process deployment). With IIS in front, IIS can serve
# these files itself and only proxy /api and /media.
_dist = Path(settings.frontend_dist)
if (_dist / "index.html").exists():
    if (_dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=str(_dist / "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        candidate = (_dist / full_path).resolve()
        try:
            candidate.relative_to(_dist.resolve())
        except ValueError:
            return FileResponse(_dist / "index.html")
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_dist / "index.html", headers={"Cache-Control": "no-cache"})
