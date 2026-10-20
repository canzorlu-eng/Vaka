# Privacy and retention (operational view)

This is the engineering inventory behind a privacy notice (KVKK / GDPR); it is not legal text. Keep it in sync when schema,
providers or retention settings change.

## Data inventory

### PostgreSQL (source of truth)

| Table | Personal data | Retention | Removed by |
|---|---|---|---|
| `users` | Google subject id, email, name, picture URL, role, timestamps | until account deletion | `DELETE /api/me` |
| `auth_sessions` | hashed session token, user id, `user_agent` (<= 200 chars) | 30 days (`SESSION_TTL_DAYS`), expired rows pruned every 5 min | cascade / maintenance loop / logout |
| `case_sessions` | everything the student typed and the simulated dialogue (`data jsonb`) - free text, may contain anything the user types | **180 days** (`RETENTION_SESSIONS_DAYS`) | maintenance loop / cascade |
| `case_reports` | scores and feedback text per session | follows its session (cascade) | cascade |
| `ai_cases` | AI-generated cases owned by the user | until account deletion (no automatic expiry) | cascade |
| `jobs` | job payload (topic/difficulty prompts) and result | **30 days** after finish (`RETENTION_JOBS_DAYS`) | maintenance loop / cascade |
| `llm_usage` | user id (nullable), model, token/char counts, cost, latency, `ref` | no expiry (cost accounting); **user id is set NULL on account deletion** | `ON DELETE SET NULL` |
| `subscriptions` | plan, status, iyzico customer/subscription references, period end | until account deletion (deletion is refused while a subscription is active/pending/past_due) | cascade |
| `payment_events` | raw iyzico webhook payloads (subscription references, order ids; **no card data**) | no automatic expiry; keep for accounting obligations, review yearly | manual |

Card numbers are entered on iyzico's pages and never reach our servers or database.

### Redis (Key Value) - disposable, no source-of-truth data

| Key | Content | TTL |
|---|---|---|
| `rl:<name>:ip:<ip>` / `rl:global:<ip>` / `rl:<name>:u:<user id>` | request counters (client IP, user id) | window (1 min - 1 h) |
| `tts:<sha256>` | synthesized patient audio (key is a hash of model|voice|text) | **7 days** |
| `score-lock:<session>`, `inflight:<user>`, `alert:<key>` | locks / de-dup markers | 90 s - 1 h |

### Logs (Render, stdout JSON)

Contain: timestamp, level, request id, user id (UUID), method, path (no query string), status, duration, job ids, error class.
Do **not** contain: request/response bodies, cookies, Authorization headers, query strings, chat text, emails, API keys or
DSNs (`logging_setup.redact` also masks key-shaped strings and `postgres://user:pass@`). Client IPs are not written by the app;
Render's edge/log infrastructure and any log drain follow their own retention (Render's default log retention is short, check your plan;
if you add a drain, set a retention <= 30 days there).

### Backups

- Our nightly dumps contain **the whole database** (all tables above) and are stored in the backup bucket: 14 daily + 8 weekly
  generations, then deleted by `backup.sh`. Maximum age of any object: about 8 weeks.
- Render's own Postgres backups: Render's window (days).
- Sidecar files (`.sha256`, `.counts`) contain only a checksum and three row counts.

### Not copied / never stored

Redis contents and logs are not backed up. Provider API keys, `SECRET_KEY` and the Google client secret are not in the database or in dumps.
Raw card data, Google access tokens (online access, discarded after the profile call) and Google passwords are never stored.

## Processors / recipients

| Provider | Receives | Purpose | Region note |
|---|---|---|---|
| Render | all application data (hosting, Postgres, Key Value, logs) | infrastructure | Frankfurt (EU) |
| Google (Sign-In) | OAuth exchange; returns email/name/picture | authentication | |
| Google Gemini API | case context and the student's messages for each AI turn, case-generation prompts, scoring input | patient simulation, generation, feedback | use the paid API tier and confirm in the provider terms that API data is not used for training |
| OpenAI | the patient's reply text to synthesize speech (pro users, only if `OPENAI_API_KEY` set) | text-to-speech | confirm API data-retention/zero-retention terms |
| iyzico | customer identity needed for subscription checkout, payment data typed on iyzico | billing | Turkey |
| Backup storage (R2/B2/S3) | encrypted-at-rest dumps of the database | disaster recovery | choose an EU/TR-appropriate region |
| Uptime/alert tools (optional) | URLs and alert text; no personal data by design | monitoring | |

## Retention summary

| Data | Period | Setting |
|---|---|---|
| Case sessions + reports | 180 days from creation | `RETENTION_SESSIONS_DAYS` |
| Jobs | 30 days after finish | `RETENTION_JOBS_DAYS` |
| Login session cookie / `auth_sessions` | 30 days | `SESSION_TTL_DAYS` |
| TTS audio cache | 7 days | `llm.TTS_CACHE_TTL` |
| Backups | 14 daily + 8 weekly | `BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY` |
| Account and AI cases | until the user deletes the account | |
| `llm_usage` (anonymised on deletion), `payment_events` | no automatic expiry | review yearly |

## User rights (implemented endpoints)

- **Access / portability**: `GET /api/me/export` (authenticated, rate limit 5 per hour) returns profile (without the Google subject id), subscription, sessions, reports, AI cases, jobs and AI-usage rows as JSON.
- **Erasure**: `DELETE /api/me` with body `{"confirm":"DELETE"}` (3 per hour). Hard-deletes the user; foreign keys cascade sessions, reports, auth sessions, jobs, AI cases and the subscription row; `llm_usage` rows are kept without the user id. Refused with 409 while a subscription is active - cancel via `POST /api/billing/cancel` first. The session cookie is cleared.
- **Rectification**: name/email/picture refresh from Google at each login.
- Redis counters/audio cache expire on their own; TTS audio is keyed by text hash and not linked to a user.

## Deleted users and backups

Deleted accounts remain inside existing backups until those age out (**<= 8 weeks**, the oldest weekly dump) and inside Render's
PITR window (days). Policy: backups are "put beyond use" - they are never browsed or restored except for disaster recovery.
**After any restore**, re-apply deletions requested since the restored dump's date (support/e-mail records of deletion requests;
the app also logs `user_id` for sign-ins, not for deletions, so keep a simple deletion log with date and user id) before the
restored database serves traffic. State the 8-week maximum in the privacy notice.

## Change checklist

New column/table holding personal data -> add it to this inventory, the export endpoint, the deletion cascade, the retention job,
and check that dumps/logs do not leak more than intended. New provider -> add to the processors table and the notice.
