# Setup guide (first deployment)

Do the steps in order. Console menus change; the names below are the ones at the time of writing. Create **separate** objects
for staging and production (marked [staging] / [prod]) - do each section twice.

Before you start: push the repo to GitHub with branches `main` and `staging` (`git switch -c staging && git push -u origin staging`),
and decide the production domain (e.g. `app.example.com`). Until the domain is ready use `https://vaka.onrender.com`
(the actual `*.onrender.com` name is shown on the service page after the first deploy; if the name is taken Render appends a suffix).

## 1. Google OAuth client (login)

1. https://console.cloud.google.com -> project selector (top bar) -> **New project** -> name `vaka` ([prod]) / `vaka-staging` ([staging]) -> **Create**.
2. Left menu -> **APIs & Services -> OAuth consent screen** (shown as *Google Auth Platform -> Branding* in the new UI).
   - User type **External** -> **Create**. App name `Vaka`, user support email, developer contact email -> **Save and continue**.
   - **Scopes** (Data Access) -> **Add or remove scopes** -> tick `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile` -> **Update -> Save**. (No sensitive scopes are needed.)
   - **Audience / Test users**: while the status is *Testing*, add the Google accounts that may log in (including yourself). To open it to everyone press **Publish app** (basic scopes need no verification).
3. **APIs & Services -> Credentials -> Create credentials -> OAuth client ID** -> Application type **Web application** -> name `vaka-web`.
   - **Authorized JavaScript origins**: `http://localhost:8001` (dev only), and the Render URL, e.g. `https://vaka.onrender.com` / `https://app.example.com`.
   - **Authorized redirect URIs** (exact match, no trailing slash):
     - `http://localhost:8001/api/auth/google/callback`
     - `https://<your-render-or-custom-host>/api/auth/google/callback`
   - **Create** -> copy **Client ID** and **Client secret** (the secret can be viewed again via the client's page).
4. Put them in `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (Render, step 2). For local dev put them in `backend/.env` (git-ignored) and set `PUBLIC_BASE_URL=http://localhost:8001`.
5. Staging gets its own project/client with the staging host in the redirect URI.
Troubleshooting: `redirect_uri_mismatch` = the URI above does not match `PUBLIC_BASE_URL + /api/auth/google/callback` character for character.

## 2. Render: deploy the Blueprint

1. https://dashboard.render.com -> sign in with GitHub -> **Workspace Settings -> Billing**: add a card (Postgres, Key Value, starter/standard instances and `preDeployCommand` need paid plans).
2. **New + -> Blueprint** -> connect/authorize the GitHub repo -> select it. Branch: `main`. Blueprint path: `render.yaml`.
3. Render shows everything to be created (2 databases, 2 Key Value, 2 web services, 4 cron jobs, 2 env groups) and asks for each `sync: false` value:
   - Production service `vaka`: `PUBLIC_BASE_URL`, `ADMIN_EMAILS` (your Google email), `GOOGLE_CLIENT_ID/SECRET` (prod client), `GEMINI_API_KEY`, `OPENAI_API_KEY`, `IYZICO_*` (leave empty until step 5; the app starts without payments), `ALERT_WEBHOOK_URL`.
   - Staging service `vaka-staging`: the same names with the **staging** values (sandbox iyzico keys).
   - Cron jobs: backup bucket values from step 3 (`BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`), `ALERT_WEBHOOK_URL`. Not ready yet? Enter a placeholder, finish step 3, then fix the values under the cron job -> **Environment**.
   - Optional values you do not have yet (iyzico, OpenAI): Render may require non-empty input; enter `todo` and replace it later. Until then payments or voice stay disabled/failing, the rest of the app works.
4. Click **Apply**. Render builds the Docker image (first build ~5-8 min), runs `alembic upgrade head` (pre-deploy), starts the service.
5. The `staging` branch must exist before applying (services with `branch: staging` track it).
6. Open `https://<service>.onrender.com/api/ready` -> `{"status":"ok","database":true,"cache":true}`. Open `/` -> the SPA; **Log in with Google**.
7. Add `PUBLIC_BASE_URL` to the Google client (step 1) if you used a placeholder, then redeploy.
8. Notifications: **Account Settings -> Notifications** (or per service) -> add Slack/Discord/e-mail for *deploy failed* and *service unhealthy / cron failed*.
9. GitHub: **Settings -> Branches -> Add rule** for `main` and `staging`: require status check **deploy gate**, require PR. (Render's `autoDeployTrigger: checksPass` then deploys only green commits.)
10. Optional: GitHub **Settings -> Secrets and variables -> Actions -> Variables**: `STAGING_URL=https://vaka-staging.onrender.com` for the smoke-test workflow.
Known limit: Render Blueprint validation can only be checked by Render; if the Apply screen reports a field error, the message names the field - fix `render.yaml`, push, **Sync** the Blueprint.

## 3. Backup bucket (Cloudflare R2 or Backblaze B2)

The bucket must be **outside Render**. Create one bucket, two prefixes (`vaka/production`, `vaka/staging`), and separate API tokens per environment if possible.

**Cloudflare R2**
1. https://dash.cloudflare.com -> **R2 Object Storage** (add a payment method; the free tier covers dumps of this size) -> **Create bucket** -> name `vaka-backups`, location **EEUR** (Eastern Europe) or the closest -> **Create**.
2. Bucket -> **Settings** -> keep public access **disabled**. Optionally add an *object lifecycle* rule to abort incomplete multipart uploads.
3. R2 overview -> **Manage R2 API Tokens -> Create API token** -> permission **Object Read & Write** -> *Specify bucket* `vaka-backups` -> TTL as you like -> **Create**. Copy **Access Key ID**, **Secret Access Key** (shown once) and the S3 endpoint `https://<account-id>.r2.cloudflarestorage.com`.
4. Values: `BACKUP_S3_ENDPOINT=https://<account-id>.r2.cloudflarestorage.com`, `BACKUP_S3_BUCKET=vaka-backups`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`. (`AWS_DEFAULT_REGION` defaults to `auto`, correct for R2.)

**Backblaze B2**
1. https://secure.backblaze.com -> **B2 Cloud Storage -> Buckets -> Create a Bucket** -> unique name, **Private**, default encryption **Enable**, Object Lock optional (recommended for ransomware protection) -> **Create**.
2. **Application Keys -> Add a New Application Key** -> restrict to the bucket, **Read and Write** -> copy **keyID** (= `AWS_ACCESS_KEY_ID`) and **applicationKey** (= `AWS_SECRET_ACCESS_KEY`; shown once).
3. `BACKUP_S3_ENDPOINT=https://s3.<region>.backblazeb2.com` (shown on the bucket page, e.g. `s3.eu-central-003.backblazeb2.com`), `AWS_DEFAULT_REGION=<region>` (e.g. `eu-central-003`; add it to the cron jobs), `BACKUP_S3_BUCKET=<bucket>`.

**Check it**: Render -> `vaka-staging-backup` -> **Trigger Run**; logs end with `OK vaka-<stamp>.dump size=...`, and the object appears under `vaka/staging/daily/`. Then trigger `vaka-staging-restore-test`; it must end with `OK schema=0001 ...`.
If the restore test fails with a `permission denied to create database`, the managed DB role lacks `CREATEDB`: create a small separate Postgres (any host) and set `RESTORE_ADMIN_URL` on the restore cron jobs to its URL.

## 4. iyzico (payments)

1. Sandbox: https://sandbox-merchant.iyzipay.com -> **Sign up** (a sandbox merchant is separate from production and needs no documents).
2. Merchant panel -> **Settings (Ayarlar) -> Company Settings (Firma Ayarlari)** -> **API Keys** - copy **API Key** and **Secret Key**. Staging: `IYZICO_API_KEY`, `IYZICO_SECRET_KEY`; `IYZICO_BASE_URL` is already `https://sandbox-api.iyzipay.com` in the staging group.
3. Subscriptions must be enabled for the merchant (iyzico *Abonelik* product; in production iyzico support activates it after contract/approval - request it early).
4. Create the product and the four plans (once per environment), from your machine with the right keys in `backend/.env` or exported (never commit):
   ```bash
   cd backend
   .venv/bin/python scripts/iyzico_setup.py --dry-run     # shows what would be created
   .venv/bin/python scripts/iyzico_setup.py               # creates "Vaka Pro" + 4 plans, prints the plan reference codes
   ```
   Copy the printed codes into `IYZICO_PLAN_MONTHLY_USD`, `IYZICO_PLAN_YEARLY_USD`, `IYZICO_PLAN_MONTHLY_TRY`, `IYZICO_PLAN_YEARLY_TRY` on the Render service and redeploy. (`PRICE_*` come from the env group and must match what the script used.)
5. Webhook: merchant panel -> **Settings -> Notifications (Bildirimler) / Webhook** -> notification URL `https://<host>/api/billing/webhook` -> enable **signature (HMAC) verification** so requests carry `x-iyz-signature-v3` (the app rejects unsigned/invalid webhooks with 401). If the panel gives a distinct webhook secret set `IYZICO_WEBHOOK_SECRET`; otherwise the app falls back to the secret key.
6. Test on staging with iyzico's sandbox test cards (listed in the iyzico docs, "Test Cards"): subscribe, confirm the `subscriptions` row becomes `active` and that a `payment_events` row appears.
7. Production: repeat with the live merchant account at https://merchant.iyzipay.com, `IYZICO_BASE_URL=https://api.iyzipay.com` (already set in the production group), run `iyzico_setup.py` with live keys, set webhook to the production host, and do one real small transaction before announcing.

## 5. Gemini and OpenAI keys with spend limits

**Gemini** ([prod] and [staging] in separate projects)
1. https://aistudio.google.com/apikey -> **Create API key** -> choose the Cloud project created in step 1 -> copy the key -> `GEMINI_API_KEY`.
2. Enable billing on that project (Studio -> the key's *Set up billing*, or Cloud Console -> **Billing**), otherwise the free-tier limits and data-use terms apply.
3. Budget alert: Cloud Console -> **Billing -> Budgets & alerts -> Create budget** -> scope: the project -> amount (e.g. $30 for prod, $5 for staging) -> thresholds 50/90/100 % -> e-mail to you. Budgets alert, they do not stop spend; the app's own caps (`USER_DAILY_COST_CAP_*`, `GLOBAL_DAILY_COST_ALERT_USD`) are the hard guard. Optionally set an API quota (APIs & Services -> Gemini API -> *Quotas*) to cap requests per day.

**OpenAI**
1. https://platform.openai.com -> **Settings -> Organization -> Projects -> Create** `vaka-prod` / `vaka-staging`.
2. **API keys -> Create new secret key** -> owner: service account or you, project `vaka-prod`, permissions **Restricted**: only *Audio -> Request* (text-to-speech) -> copy once -> `OPENAI_API_KEY`.
3. **Settings -> Limits** (project): set a **monthly budget** and a **notification threshold** (e.g. $20 / alert at $10 for prod; $5 for staging). In org *Billing* use **prepaid credits** with auto-recharge **off** so a runaway cannot exceed the balance.

After both: watch the first week's `llm_usage` (admin overview) against the provider dashboards; adjust `PRICE_*` / caps.

## 6. Alert webhook

Slack: https://api.slack.com/apps -> **Create New App -> From scratch -> Incoming Webhooks -> On -> Add New Webhook to Workspace** -> pick the channel -> copy the URL. Discord: channel **Edit -> Integrations -> Webhooks -> New Webhook -> Copy Webhook URL** (append `/slack` is not needed; the app sends both `text` and `content`). Use one webhook per environment as `ALERT_WEBHOOK_URL`. Test it:
`curl -X POST -H 'Content-Type: application/json' -d '{"text":"vaka alert test","content":"vaka alert test"}' "$ALERT_WEBHOOK_URL"`.

## 7. Local development

```bash
docker compose -f docker-compose.dev.yml up -d           # Postgres :55432 (vaka/vaka), Redis :56379
cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp .env.example .env        # fill DATABASE_URL=postgresql://vaka:vaka@localhost:55432/vaka, REDIS_URL=redis://localhost:56379/0, SECRET_KEY (>= 32 chars), GOOGLE_*, GEMINI_*
AUTO_MIGRATE=true .venv/bin/uvicorn server:app --reload --port 8001
cd ../frontend && npm ci --legacy-peer-deps && npm install --no-save --legacy-peer-deps ajv@8 && npm start
cd ../backend && .venv/bin/pytest -q      # uses a throw-away database vaka_test on the dev Postgres
```
