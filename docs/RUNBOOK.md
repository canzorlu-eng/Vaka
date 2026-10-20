# Runbook

Environments (all defined in `render.yaml`, frankfurt):

| | production | staging |
|---|---|---|
| Git branch | `main` | `staging` |
| Web service | `vaka` | `vaka-staging` |
| Postgres / Key Value | `vaka-db` / `vaka-redis` | `vaka-staging-db` / `vaka-staging-redis` |
| Config group | `vaka-prod-config` | `vaka-staging-config` |
| Cron jobs | `vaka-backup`, `vaka-restore-test` | `vaka-staging-backup`, `vaka-staging-restore-test` |
| Payments | iyzico LIVE | iyzico SANDBOX |

First-time setup: [SETUP_GUIDE.md](SETUP_GUIDE.md). Everything below assumes it is done.

## Deploy

1. Open a PR into `main` (or `staging`). CI (`.github/workflows/ci.yml`) must pass: ruff, pytest with Postgres 16 + Redis 7,
   `alembic upgrade head` on an empty DB, `pip-audit`, frontend build with `CI=true`, Docker build + container smoke test,
   gitleaks, and the aggregate **deploy gate** job.
2. Merge. Render's `autoDeployTrigger: checksPass` builds the Docker image once the GitHub checks are green.
3. Render runs `preDeployCommand: alembic upgrade head` in the new image **before** switching traffic. If it fails the deploy
   is aborted and the old version keeps serving. Then Render starts the new instance, waits for `GET /api/health` = 200, and
   routes traffic; the old instance gets SIGTERM and drains (see "Graceful shutdown").
4. Verify: Render deploy log, then `curl -fsS https://<host>/api/ready` (expects `{"status":"ok","database":true,"cache":true}`),
   then watch logs for `level=ERROR` for 10 minutes.

`AUTO_MIGRATE` is `false` in both deployed environments on purpose: migrations run exactly once, from `preDeployCommand`,
not from every booting instance.

## Staging to production promotion

1. Merge the feature into `staging`; wait for the staging deploy.
2. Run **Actions -> Smoke test (staging / any URL)** with the staging URL (health, ready, SPA + CSP header, catalogue, auth refusal).
3. Manual checks on staging: Google login, start a session, AI chat turn, score report; for billing changes complete a
   sandbox checkout and confirm the webhook arrived (`payment_events` row).
4. Check the staging backup cron succeeded last night and that `vaka-staging-restore-test` is green (schema about to ship
   has been restored from a real dump).
5. Open a PR `staging` -> `main` (fast-forward / merge commit, no squash, so the same commits are in both). Merge after CI.
6. Watch the production deploy as in "Deploy". Keep the previous deploy's Render page open for rollback.

Every secret differs between the two environments; promotion only moves code, never configuration.
New env var? Add it to `render.yaml` first (value or `sync: false`), merge, then fill it in the dashboard of **both** services
before the release that needs it. `config.validate()` fails fast at boot for missing `DATABASE_URL`/`SECRET_KEY` (and
`REDIS_URL` / https `PUBLIC_BASE_URL` in production), so a bad configuration fails the health check and the old version stays live.

## Rollback

**Code only (no migration in the release):** Render dashboard -> service -> Events/Deploys -> pick the last good deploy -> *Rollback*.
Takes about a minute and does not rebuild.

**Release with a migration:** Alembic here is forward-only (`0001.downgrade` raises on purpose; never drop production data to
"undo" a release). Therefore every migration must follow **expand / contract** so the previous code version still runs on
the new schema:

- *Expand release N*: add nullable columns/new tables/new indexes (`CREATE INDEX CONCURRENTLY`), dual-write if needed. Old code ignores them.
- *Release N+1*: switch reads to the new structure. Rolling back to N is safe.
- *Contract release N+2 (weeks later, after N+1 is proven)*: drop old columns/tables. This migration is the point of no
  return; take a manual backup first (`vaka-backup` -> *Trigger Run*), and review it in the PR as destructive.
- Never in one release: rename a column, change a type, add `NOT NULL` without default, drop anything still read by the previous version.

So the rollback is always "redeploy the previous image", and the already-applied expand migration stays in place.
If a migration itself is wrong: fix forward with a new migration; as a last resort follow [DISASTER_RECOVERY.md](DISASTER_RECOVERY.md) (point-in-time restore).

## Graceful shutdown

Render sends SIGTERM on deploy/restart and SIGKILLs after `maxShutdownDelaySeconds` (30). The process uses
`--timeout-graceful-shutdown 25`; the lifespan stops job workers (20 s grace). Jobs interrupted by SIGKILL are recovered
because the lease (`locked_until`) expires and another worker re-claims them (attempt counter +1). Do not raise
`JOB_TIMEOUT_S` above what you can lose: a job longer than the shutdown window will simply be retried after a deploy.

## Domain, HTTPS, CORS

1. Render -> service `vaka` -> Settings -> *Custom Domains* -> *Add*: `app.example.com`. Create the DNS record Render shows
   (CNAME to `vaka.onrender.com` for a subdomain; for an apex use the A/ALIAS values Render lists). Wait for *Verified* and
   the certificate (Let's Encrypt, automatic; HTTP is redirected to HTTPS by Render).
2. Set `PUBLIC_BASE_URL=https://app.example.com` (no trailing slash) on the service and save (redeploys).
   This value drives: cookie `Secure` flag, HSTS, the CSRF origin allow-list, and the Google redirect URI
   `https://app.example.com/api/auth/google/callback`.
3. Add that redirect URI (and the JavaScript origin) to the Google OAuth client; update the iyzico webhook URL to
   `https://app.example.com/api/billing/webhook`.
4. CORS: the SPA is served by the same service, so **leave `CORS_ORIGINS` empty**. Only set it (comma separated, https origins)
   if a separate frontend host calls this API; the CSRF middleware allows `PUBLIC_BASE_URL` plus `CORS_ORIGINS`.
5. Keep `vaka.onrender.com` working or disable it; if you keep both, the non-primary host cannot log in (its origin is not allowed), which is intended.
6. Verify: `curl -sI https://app.example.com/ | grep -iE 'strict-transport|content-security'`.

## Alerts and monitoring

| Layer | What | Setup |
|---|---|---|
| Render notifications | deploy failed, service crashed/unhealthy, cron job failed | Account/Workspace Settings -> *Notifications* -> Slack/Discord/email; also per service. Cron failures (backup, restore test) arrive here because the scripts exit non-zero. |
| Uptime check | external probe of `https://<host>/api/health` every 1-5 min | UptimeRobot / Better Stack / Cloudflare Health Check, alert by email + the same channel. Use `/api/ready` as a second check with keyword `"database":true`. |
| App alerts | `ALERT_WEBHOOK_URL` (Slack/Discord-compatible incoming webhook) | Posts for daily AI spend >= `GLOBAL_DAILY_COST_ALERT_USD` and other `alerts.send()` calls; de-duplicated for 1 h through Redis. Backup scripts post to the same URL on failure. Use a separate webhook/channel per environment. |
| Errors (optional) | Sentry | Not wired in code. If wanted: add `sentry-sdk[fastapi]` to `requirements.txt`, call `sentry_sdk.init(dsn=os.environ["SENTRY_DSN"], send_default_pii=False, traces_sample_rate=0.0)` in `server.py`, add `SENTRY_DSN` as `sync: false`. Scrub request bodies and cookies; see PRIVACY_AND_RETENTION.md. |

**Logs** (Render -> service -> Logs, or log streams to Better Stack/Datadog): one JSON object per line:
`ts, level, logger, msg, request_id, user_id, env` plus per-event fields (`method, path, status, duration_ms`, `job_id`, ...).
`vaka.access` lines exist for every `/api/*` request except `/api/health`; slow ones are WARNING `slow request`.
Secrets in messages and exception text are redacted (`logging_setup.redact`).

*Trace one request:* every response carries `X-Request-ID`; unhandled errors return `{"detail": "Internal server error", "request_id": "..."}`.
Ask the user for that id (or read it from the browser network tab) and search the logs for the id; you get the access line,
and any error/stack trace logged during the same request (`request_id` is set in a contextvar). A client may also send its own
`X-Request-ID` (<= 64 alphanumeric/dash chars) to correlate a support session.

## Incident checklist

1. **Acknowledge** in the alert channel; note the start time and the last deploy time (Render *Events*).
2. **Scope**: `curl https://<host>/api/health` (process), `/api/ready` (database/cache), Render status page, Gemini/OpenAI/iyzico status pages.
3. **Recent change?** If the incident began with a deploy -> roll back first, investigate second ([Rollback](#rollback)).
4. **Read logs**: filter `level:ERROR` and `slow request`; follow one `request_id`.
5. Common causes:
   - `/api/ready` 503 `database:false`: Postgres down/maintenance/connection exhaustion (check Render DB *Metrics*; pool max is `DB_POOL_MAX`=10 per instance).
   - `degraded` with `cache:false`: Key Value down; rate limits fail open, TTS cache cold. Not an outage.
   - Chat/scoring failing, `daily_ai_budget_reached` (429): per-user daily cap; global cost alert -> check `llm_usage`, consider lowering caps.
   - Jobs stuck `processing`: lease expires after `JOB_TIMEOUT_S + 30` s and the job is retried; permanent failures show `error` in `jobs`.
   - Gemini 429/5xx: provider outage or quota; the UI degrades, jobs retry with backoff.
   - OAuth login loop: `PUBLIC_BASE_URL` or Google redirect URI mismatch, or a non-primary host.
   - Webhook 401: wrong `IYZICO_WEBHOOK_SECRET` or signature option not enabled.
6. **Mitigate** (restart service, roll back, raise plan size, temporarily lower `GLOBAL_IP_LIMIT_PER_MIN`, revoke a leaked key - see SECURITY.md).
7. **Data damage?** Stop writes if needed and go to DISASTER_RECOVERY.md before "fixing" data.
8. **Communicate**, then write a short post-mortem (timeline, cause, what detection missed, follow-ups).

## Routine

- Weekly: look at the Monday restore-test result (Render notifications) and the AI-spend alert history.
- Monthly: review Dependabot PRs, `pip-audit`/`npm audit` output in CI, Render plan usage.
- Quarterly: restore drill ([DISASTER_RECOVERY.md](DISASTER_RECOVERY.md)), rotate keys that are due (SECURITY.md).

## Requested app changes (not done here, outside DevOps scope)

- `backend/billing.py`: add a `python -m billing` entry point (connect `db`/`cache`, `await reconcile_all()`, close, exit non-zero on error) to enable the commented `vaka-billing-reconcile` cron in `render.yaml`.
- `frontend/package.json`: add `"ajv": "^8.17.0"` to `devDependencies` and then delete the `npm install --no-save ... ajv@8` workaround lines in `Dockerfile` and `ci.yml`.
