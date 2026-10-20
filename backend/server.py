"""Vaka API application: wiring only (settings, lifespan, middleware, routers, SPA hosting).
Business logic lives in the modules imported below."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.cors import CORSMiddleware

import cache
import db
import job_handlers  # noqa: F401  (registers background job handlers)
import jobs
import logging_setup
from config import settings
from middleware import (BodyLimitMiddleware, CsrfOriginMiddleware, GlobalRateLimitMiddleware,
                        RequestContextMiddleware)

logging_setup.setup()
logger = logging.getLogger("vaka")
ROOT_DIR = Path(__file__).parent
FRONTEND_BUILD = ROOT_DIR.parent / "frontend" / "build"


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config
    cfg = Config(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT_DIR / "migrations"))
    cfg.attributes["skip_logging"] = True
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate()
    if settings.auto_migrate:
        await asyncio.to_thread(_migrate)
    await db.connect()
    await cache.init()
    stop = asyncio.Event()
    tasks = [asyncio.create_task(jobs.worker_loop(stop, f"w{i}")) for i in range(settings.job_workers)]
    tasks.append(asyncio.create_task(jobs.maintenance_loop(stop)))
    logger.info("startup complete", extra={"extra_fields": {"cache": cache.backend(), "env": settings.env}})
    try:
        yield
    finally:  # graceful shutdown: stop claiming jobs, let in-flight work finish (or its lease expire), close pools
        stop.set()
        done, pending = await asyncio.wait(tasks, timeout=20)
        for t in pending:
            t.cancel()
        await cache.close()
        await db.close()
        logger.info("shutdown complete")


app = FastAPI(title="Vaka API", lifespan=lifespan, docs_url=None if settings.is_prod else "/api/docs",
              redoc_url=None, openapi_url=None if settings.is_prod else "/api/openapi.json")

# Middleware: added innermost -> outermost.
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type", "Idempotency-Key", "X-Request-ID"])
app.add_middleware(CsrfOriginMiddleware)
app.add_middleware(GlobalRateLimitMiddleware, per_minute=settings.global_ip_limit_per_min)
app.add_middleware(BodyLimitMiddleware, max_bytes=settings.max_body_bytes)
app.add_middleware(RequestContextMiddleware)

import auth  # noqa: E402
import routes_account  # noqa: E402
import routes_catalogue  # noqa: E402
import routes_jobs  # noqa: E402
import routes_sessions  # noqa: E402

for module in (auth, routes_catalogue, routes_sessions, routes_jobs, routes_account):
    app.include_router(module.router)
try:  # payments module is optional until iyzico credentials are configured
    import billing
    app.include_router(billing.router)
except ModuleNotFoundError:
    logger.info("billing module not installed")


@app.get("/api/health", include_in_schema=False)
async def health():
    """Liveness: the process is up (no dependencies, used by the platform health check)."""
    return {"status": "ok"}


@app.get("/api/ready", include_in_schema=False)
async def ready():
    """Readiness: dependencies reachable."""
    checks = {"database": await db.ping(), "cache": await cache.ping()}
    return JSONResponse({"status": "ok" if all(checks.values()) else "degraded", **checks},
                        status_code=200 if checks["database"] else 503)


if FRONTEND_BUILD.is_dir():
    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        target = (FRONTEND_BUILD / path).resolve()
        if path and target.is_file() and FRONTEND_BUILD.resolve() in target.parents:
            headers = {"Cache-Control": "public, max-age=31536000, immutable"} if path.startswith("static/") else {}
            return FileResponse(target, headers=headers)
        return FileResponse(FRONTEND_BUILD / "index.html", headers={"Cache-Control": "no-cache"})
