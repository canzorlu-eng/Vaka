# Architecture

Vaka is one deployable: a **FastAPI** process that serves the JSON API (`/api/*`) and the built **React** single-page app
(`frontend/build`, served by `server.py` for every non-`/api` path). State lives in **PostgreSQL**; **Redis** (Render Key
Value) holds only disposable data. Everything that talks to a paid provider (Gemini, OpenAI TTS, iyzico) is behind the
backend; the browser never sees a provider key.

```
Browser (React SPA)
   |  HTTPS (Render edge: TLS, custom domain)
   v
Render web service  "vaka"  (Docker, 1 instance, 1 uvicorn process)
   |-- middleware: RequestContext (request id, access log, security headers/CSP) -> BodyLimit -> GlobalRateLimit
   |               -> CsrfOrigin -> [CORS only if CORS_ORIGINS set] -> routers
   |-- routers: auth, catalogue, sessions, jobs, account/admin, billing
   |-- in-process background tasks: JOB_WORKERS x jobs.worker_loop + 1 x jobs.maintenance_loop
   |-- PostgreSQL (asyncpg pool)   source of truth
   |-- Redis (cache.py)            rate limits, locks, TTS audio cache, alert de-dup (falls back to in-process memory if REDIS_URL empty)
   `-- outbound: Google OAuth, Gemini (google-genai), OpenAI TTS, iyzico REST, ALERT_WEBHOOK_URL
Render cron jobs (Dockerfile.backup): nightly pg_dump -> S3-compatible bucket; weekly restore drill
```

## Request flow

1. `RequestContextMiddleware` assigns `request_id` (accepts a sane inbound `X-Request-ID`), puts it in a contextvar, wraps the
   response with security headers and `X-Request-ID`, and writes one JSON access-log line per `/api/*` call (no bodies,
   headers or query strings). Requests slower than `SLOW_REQUEST_S` (2 s) log at WARNING.
2. `BodyLimitMiddleware` rejects bodies above `MAX_BODY_BYTES` (413). `GlobalRateLimitMiddleware` counts per client IP
   (`GLOBAL_IP_LIMIT_PER_MIN`, 429). `CsrfOriginMiddleware` requires an allowed `Origin`/`Referer` on state-changing requests
   that carry the session cookie (exempt: `/api/billing/webhook`, which is authenticated by signature).
3. Auth is a server-side session: the `vaka_session` cookie holds a random token; only its hash is stored in
   `auth_sessions`. Per-route limits are dependencies (`ratelimit.limit`), authorization is enforced in SQL (`user_id` in
   every case-session query).
4. Client IP comes from uvicorn `--proxy-headers --forwarded-allow-ips='*'` (Render's proxy sets `X-Forwarded-For`).

## Slow work: the jobs table

AI case generation is a job, not a request: `POST /api/cases/generate` inserts a row in `jobs` (idempotent on
`(user_id, kind, idempotency_key)`), returns 202, and the client polls `GET /api/jobs/{id}`.
`jobs.worker_loop` claims work with `UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)` and a lease
(`locked_until = now + JOB_TIMEOUT_S + 30`). A crashed or killed process just lets the lease expire; another worker resumes.
Retries use exponential backoff up to `JOB_MAX_ATTEMPTS`. `maintenance_loop` (every 5 min) deletes expired auth sessions,
jobs older than `RETENTION_JOBS_DAYS`, case sessions older than `RETENTION_SESSIONS_DAYS`, marks abandoned jobs failed and
raises the `GLOBAL_DAILY_COST_ALERT_USD` alert.

Because workers and the maintenance loop live in the web process, **run exactly one instance** unless you accept N copies
of the maintenance loop (harmless but wasteful) and keep Redis configured. Horizontal scaling later = set `numInstances`
and `JOB_WORKERS` consciously; the `SKIP LOCKED` claim is already multi-worker safe.

## Graceful shutdown

Render sends SIGTERM, waits `maxShutdownDelaySeconds` (30 in `render.yaml`), then SIGKILL. uvicorn stops accepting connections and
drains in-flight requests for up to `--timeout-graceful-shutdown 25`. The FastAPI lifespan then sets the stop event, gives
workers 20 s to finish (otherwise cancels; the job lease makes that safe), closes Redis and the DB pool.
Measured locally: `docker stop` of an idle container logs "job worker stopped", "shutdown complete" and exits in < 1 s.

## Data model (migration `0001_initial_schema`)

| Table | Purpose | Notes |
|---|---|---|
| `users` | Google identity (`google_sub` unique, `lower(email)` unique), `role` user/admin | created on first login; `ADMIN_EMAILS` promote |
| `auth_sessions` | cookie token hash -> user, `expires_at` | pruned by maintenance loop |
| `case_sessions` | one simulated patient encounter, whole state in `data jsonb` | `ON DELETE CASCADE` from users; retention 180 d |
| `case_reports` | score report per session (1:1, PK `session_id`) | cascades with the session |
| `ai_cases` | AI-generated cases, owner `created_by` (NULL = legacy shared) | |
| `jobs` | durable work queue | partial index `jobs_claim_idx`; retention 30 d |
| `llm_usage` | ledger of every LLM/TTS call with token counts and USD cost | `user_id` set NULL on user deletion (anonymous cost rows kept) |
| `subscriptions` | one row per user, iyzico subscription state | |
| `payment_events` | webhook idempotency/audit (`UNIQUE(provider, event_id)`) | |
| `alembic_version` | migration head | |

Built-in cases (`backend/cases/**`) are JSON files loaded in memory (`case_store.py`); anonymous catalogue endpoints
(`/api/topics`, `/api/cases`, `/api/cases/{id}`) therefore never touch Postgres.

Migrations are raw SQL in `backend/migrations/versions/`, applied by `alembic upgrade head`:
in Render by `preDeployCommand` (before traffic moves), in dev by `AUTO_MIGRATE=true` at startup.
Rules: see [RUNBOOK.md](RUNBOOK.md#rollback) (expand/contract).

## Environment variables

Single source: `backend/config.py` (plus `middleware.py` for CSP and `SLOW_REQUEST_S`). `S` = secret (set with `sync: false`, never
in git). Defaults shown are the code defaults.

| Variable | Default | S | Purpose |
|---|---|---|---|
| `APP_ENV` | `development` | | `development` / `staging` / `production`; production enforces https `PUBLIC_BASE_URL` and `REDIS_URL`, hides `/api/docs` |
| `PUBLIC_BASE_URL` | `http://localhost:8001` | | public origin, no trailing slash; OAuth redirect `<base>/api/auth/google/callback`; cookies are `Secure` iff https |
| `CORS_ORIGINS` | empty | | extra allowed origins (comma). Empty = same-origin only (the Render setup) |
| `LOG_LEVEL` | `INFO` | | |
| `AUTO_MIGRATE` | true in development, else false | | run Alembic at startup (dev only) |
| `DATABASE_URL` | - (required) | S | Postgres DSN |
| `DB_POOL_MAX` / `DB_COMMAND_TIMEOUT` | 10 / 30 | | asyncpg pool size / statement timeout (s) |
| `REDIS_URL` | empty (required in production) | S | Key Value connection string |
| `SECRET_KEY` | - (required, >= 32 chars) | S | signs the OAuth state cookie |
| `SESSION_TTL_DAYS` | 30 | | session cookie / `auth_sessions` lifetime |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | empty | S (secret) | Google OAuth web client |
| `ADMIN_EMAILS` | empty | | comma list; matching Google emails get `role=admin` (pro entitlements + admin endpoints) |
| `GEMINI_API_KEY` | empty | S | patient role-play, case generation, scoring text |
| `GEMINI_MODEL` / `GEMINI_THINKING_BUDGET` | `gemini-3.5-flash-lite` / -1 | | |
| `OPENAI_API_KEY` | empty | S | TTS only; without it the browser voice is used |
| `OPENAI_TTS_MODEL` / `OPENAI_TTS_VOICE` | `tts-1` / `coral` | | |
| `LLM_TIMEOUT_MS` / `LLM_MAX_CONCURRENCY` | 45000 / 8 | | |
| `PRICE_GEMINI_IN_PER_M` / `PRICE_GEMINI_OUT_PER_M` / `PRICE_TTS_PER_M_CHARS` | 0.75 / 3.75 / 15 | | cost-tracking fallbacks for models not in `usage.MODEL_PRICES` |
| `USER_DAILY_COST_CAP_FREE_USD` / `..._PRO_USD` | 0.25 / 1.50 | | hard per-user daily AI spend cap |
| `GLOBAL_DAILY_COST_ALERT_USD` | 20 | | alert threshold (webhook) |
| `ALERT_WEBHOOK_URL` | empty | S | Slack/Discord-compatible incoming webhook |
| `MAX_BODY_BYTES` / `MAX_CHAT_CHARS` / `GLOBAL_IP_LIMIT_PER_MIN` | 32768 / 600 / 300 | | |
| `JOB_WORKERS` / `JOB_TIMEOUT_S` / `JOB_MAX_ATTEMPTS` | 2 / 180 / 3 | | |
| `RETENTION_SESSIONS_DAYS` / `RETENTION_JOBS_DAYS` | 180 / 30 | | |
| `IYZICO_API_KEY` / `IYZICO_SECRET_KEY` | empty | S | |
| `IYZICO_WEBHOOK_SECRET` | empty (falls back to secret key) | S | webhook signature (`x-iyz-signature-v3`) |
| `IYZICO_BASE_URL` | `https://sandbox-api.iyzipay.com` | | prod: `https://api.iyzipay.com` |
| `IYZICO_PLAN_MONTHLY_USD`, `..._YEARLY_USD`, `..._MONTHLY_TRY`, `..._YEARLY_TRY` | empty | | plan reference codes printed by `scripts/iyzico_setup.py` |
| `PRICE_MONTHLY_USD` / `PRICE_YEARLY_USD` / `PRICE_MONTHLY_TRY` / `PRICE_YEARLY_TRY` | 9 / 90 / 399 / 3990 | | must match the iyzico plans |
| `CSP_EXTRA_SCRIPT`, `CSP_EXTRA_CONNECT`, `CSP_EXTRA_FRAME`, `CSP_EXTRA_FORM` | empty | | extra origins appended to `script-src` / `connect-src` / `frame-src` (default `'none'`) / `form-action`; space or comma separated. Default CSP is `script-src 'self'`, so the SPA build must not inline scripts (`INLINE_RUNTIME_CHUNK=false`, already set in the Dockerfile) |
| `SLOW_REQUEST_S` | 2.0 | | slow-request WARNING threshold |
| `PORT` | 10000 (Render sets it) | | listen port |

Backup/restore scripts (cron jobs only, not the web service): `BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`, `AWS_ACCESS_KEY_ID`,
`AWS_SECRET_ACCESS_KEY` (S), `BACKUP_PREFIX`, `BACKUP_TARGET=file:///dir` (tests), `BACKUP_KEEP_DAILY` (14), `BACKUP_KEEP_WEEKLY` (8),
`RESTORE_ADMIN_URL`, `RESTORE_MAX_AGE_HOURS` (36).

## Redis keys (all disposable)

`rl:<name>:<ip|u:uid>` rate-limit counters (TTL = window), `rl:global:<ip>` (60 s), `score-lock:<sid>` (90 s),
`inflight:<uid>` LLM concurrency slots (120 s), `tts:<sha256>` cached audio (7 d), `alert:<key>` alert de-dup (default 1 h).
Losing Redis loses nothing but cache warmth and the current rate-limit windows. If Redis is down the limiter fails **open**
(`cache.incr` logs "failing open"); `/api/ready` reports `cache:false` but stays 200.

## Database indexes (measured review)

Method: `backend/scripts/db_indexes_check.sql` against a scratch database with 100k `case_sessions`, 100k `llm_usage`,
100k `jobs`, ~60k `case_reports`, 20k `auth_sessions`, 2000 users (skewed so one user has ~1.5k sessions), PostgreSQL 16.

| Query (module) | Plan | Execution |
|---|---|---|
| `list_sessions` keyset page (repo) | Index Scan `case_sessions_user_created_idx` + PK lookups on `case_reports` | 0.16 ms |
| `get_session` / `get_report` | PK | 0.02 ms |
| `count_sessions_this_month` | Index Only Scan `case_sessions_user_created_idx` | 0.05 ms |
| `user_for_token` (every authed request) | PK + PK | 0.04 ms |
| `jobs._claim` | Index Scan `jobs_claim_idx` (partial) | 0.24 ms |
| `generations_this_month` (plans) | Bitmap scan `jobs_user_idx` (720 rows for the heaviest user) | 0.21 ms |
| `user_spend_24h` / `global_spend_today` (usage) | `llm_usage_user_time_idx` / `llm_usage_time_idx` | 0.04 / 0.51 ms |
| maintenance: delete expired `auth_sessions` | `auth_sessions_expiry_idx` | 2.4 ms (7k rows) |
| maintenance: delete old `jobs` | **Seq Scan** (no index on `finished_at`) | 31 ms first run (50k rows deleted); **8 ms steady state** at 50k live rows |
| maintenance: delete old `case_sessions` | **Seq Scan** first run (10k rows, 103 ms incl. cascade to reports); steady state: full scan of `case_sessions_user_created_idx` | 1.4 ms |
| `list_ai_cases` (OR on `created_by`) | Seq Scan on an empty/small table | < 0.1 ms |

Findings:

1. All request-path queries are index-backed and well under 1 ms at 100k rows. **No index is needed for user-facing latency.**
2. The only seq scans are the 5-minute retention deletes on `jobs.finished_at` and `case_sessions.created_at`. They grow
   linearly with table size (~8 ms at 50k rows, so ~80 ms at 500k) and run in the background, so this is **not urgent**;
   revisit when `jobs` exceeds ~500k live rows or `pg_stat_statements` shows the delete in the top 10 by total time.
3. No unindexed foreign keys (section 3 of the script is empty). `case_reports_user_idx` shows `idx_scan = 0` in the sample
   because no per-user report listing ran; it is still the support for `ON DELETE CASCADE` from `users`, keep it.
4. Redis caching: nothing to add. Anonymous catalogue reads are CPU-bound in-process (no DB); see the load-test numbers below.

**Proposed migration (NOT applied; create `backend/migrations/versions/0002_retention_indexes.py` when finding 2 bites):**

```python
"""Retention-delete indexes (expand-only, safe to roll back by dropping the indexes)."""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction (env.py uses transaction_per_migration=True)
    with op.get_context().autocommit_block():
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS jobs_finished_idx ON jobs (finished_at) WHERE finished_at IS NOT NULL")
        op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS case_sessions_created_idx ON case_sessions (created_at)")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS jobs_finished_idx")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS case_sessions_created_idx")
```

Measured with those indexes on the scratch DB: jobs delete 8 ms -> 0.02 ms, case_sessions delete 1.4 ms -> 0.02 ms; sizes 1.1 MB
and 2.0 MB at 100k rows (write overhead: one more index entry per insert). Upgrade note: `0001.downgrade` raises on purpose;
that does not affect `0002` because it only depends on `0001`.

## Load test (single process, local, 2026-10-20)

`backend/scripts/loadtest.py` against `uvicorn server:app` on localhost (Postgres 16 + Redis 7 in Docker, load generator
on the same laptop, `GLOBAL_IP_LIMIT_PER_MIN` raised so the limiter does not answer 429), 15 s per run, mix 20 % `/api/topics`,
30 % `/api/cases`, 50 % `/api/cases/{id}`:

| Concurrency | Throughput | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|
| 10 | 1434 req/s | 6.1 ms | 13.7 ms | 38.4 ms | 0 % |
| 50 | 792 req/s | 42 ms | 190 ms | 310 ms | 0 % |
| 100 | 873 req/s | 81 ms | 328 ms | 513 ms | 0 % |

The server process and the (also single-threaded) generator both sat at 75-90 % of a core, so these are conservative,
laptop-grade numbers: one Python process serves roughly 800-1400 anonymous catalogue req/s with zero errors and no DB
access. Authenticated paths are dominated by Gemini latency (seconds), not by this process. Conclusion: no caching layer needed
beyond what exists (HTTP `Cache-Control` on catalogue responses, Redis for limits/TTS). Re-measure on the real Render instance
with `--base-url https://<staging>` before launch.

## Scaling notes

- Vertical first (plan size). The single process is async; CPU-bound work is only JSON serialization of catalogue cases.
- `DB_POOL_MAX` (10) x instances must stay below the Postgres plan's connection limit.
- Moving to N instances is supported by the design (Redis for shared state, `SKIP LOCKED` jobs) but untested: run the
  staging environment with 2 instances and `loadtest.py` before enabling it in production.
