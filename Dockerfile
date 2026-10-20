# syntax=docker/dockerfile:1
# ---- stage 1: build the React app (same-origin API => empty backend URL) ----
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps --no-audit --no-fund
COPY frontend/ ./
# INLINE_RUNTIME_CHUNK=false: CRA must not inline the webpack runtime, otherwise the CSP (script-src 'self') blocks it.
ENV REACT_APP_BACKEND_URL="" GENERATE_SOURCEMAP=false CI=false INLINE_RUNTIME_CHUNK=false
RUN npm run build

# ---- stage 2: FastAPI serving the API and the built frontend ----
FROM python:3.15-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PORT=10000
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
# Application code, alembic.ini and migrations/ (needed by `alembic upgrade head` in the Render preDeployCommand).
COPY backend/ ./
COPY --from=web /web/build /app/frontend/build
RUN useradd --system --uid 10001 --no-create-home vaka && chown -R vaka /app
USER vaka
EXPOSE 10000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import os,sys,urllib.request as u; sys.exit(0 if u.urlopen('http://127.0.0.1:%s/api/health' % os.environ.get('PORT','10000'), timeout=4).status == 200 else 1)"
# Single process on purpose: the job workers run in-process (jobs.worker_loop) and per-process caches rely on Redis in prod.
# --timeout-graceful-shutdown 25: lifespan waits up to 20 s for in-flight jobs (server.py); Render sends SIGTERM then SIGKILL after 30 s.
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 25"]
