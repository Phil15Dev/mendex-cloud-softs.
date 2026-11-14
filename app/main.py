import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

import app.models  # noqa: F401
from app.core.config import check_production_settings, settings
from app.core.database import SessionLocal, engine
from app.core.exceptions import NeedLogin, PermissionDenied
from app.core.logging import access_middleware, setup_logging
from app.core.templating import render
from app.modules.admin.router import router as admin_router
from app.modules.auth.router import COOKIE, router as auth_router
from app.modules.auth.service import bootstrap_admin
from app.modules.customers.router import router as customers_router
from app.modules.reports.router import router as reports_router
from app.modules.requests.admin_router import router as requests_admin_router
from app.modules.requests.public_router import router as public_router
from app.modules.services.router import router as services_router
from app.modules.services.service import seed_services

log = logging.getLogger("app")

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' https://fonts.googleapis.com; "
       "font-src https://fonts.gstatic.com; script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'")


def ensure_migrated() -> None:
    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables or "admin_accounts" not in tables:
        raise RuntimeError("The database is not set up. Run: alembic upgrade head")


def startup_seed() -> None:
    with SessionLocal() as db:
        seed_services(db)
        bootstrap_admin(db)
        if settings.admin_password == "change-me-now":
            log.warning("ADMIN_PASSWORD is still the default. Change it in .env before going live.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging(settings.debug)
    check_production_settings()
    ensure_migrated()
    startup_seed()
    yield


app = FastAPI(title=settings.business_name, lifespan=lifespan,
              docs_url="/docs" if settings.debug else None, redoc_url=None,
              openapi_url="/openapi.json" if settings.debug else None)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, same_site="lax", https_only=settings.https_only,
                   max_age=60 * 60, session_cookie="flash")  # only carries one-time messages, never login state
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
for r in (public_router, auth_router, reports_router, requests_admin_router, services_router,
          customers_router, admin_router):
    app.include_router(r)


@app.middleware("http")
async def security_layer(request: Request, call_next):
    path, is_admin = request.url.path, request.url.path.startswith("/admin")
    if is_admin and request.method == "POST":  # block form posts that come from another website
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return PlainTextResponse("Cross-site request blocked.", status_code=403)
    response = await call_next(request)
    h = response.headers
    h["X-Content-Type-Options"] = "nosniff"
    h["X-Frame-Options"] = "DENY"
    h["Referrer-Policy"] = "strict-origin-when-cross-origin"
    h["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if not (settings.debug and path in ("/docs", "/openapi.json")):
        h["Content-Security-Policy"] = CSP
    if settings.https_only:
        h["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if is_admin:
        h["Cache-Control"] = "no-store"
        h["X-Robots-Tag"] = "noindex"
    return response


app.middleware("http")(access_middleware)


@app.exception_handler(NeedLogin)
async def need_login(_: Request, __: NeedLogin):
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(COOKIE, path="/admin")
    return response


@app.exception_handler(PermissionDenied)
async def denied(request: Request, exc: PermissionDenied):
    return render(request, "errors/403.html", {"message": exc.message}, 403)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    if exc.status_code == 404:
        return render(request, "errors/404.html", {}, 404)
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def invalid(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/api"):
        return JSONResponse({"detail": [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]}, status_code=422)
    return render(request, "errors/404.html", {"bad_request": True}, 400)


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    log.exception("unhandled error", extra={"request_id": getattr(request.state, "request_id", "")})
    return render(request, "errors/500.html", {"request_id": getattr(request.state, "request_id", "")}, 500)


@app.get("/health", tags=["ops"])
def health():
    return {"ok": True}


@app.get("/health/ready", tags=["ops"])
def ready():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"ok": True, "database": "up"}
    except Exception:
        return JSONResponse({"ok": False, "database": "down"}, status_code=503)
