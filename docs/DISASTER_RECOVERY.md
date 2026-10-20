# Disaster recovery

## Targets

| | Target | How it is met |
|---|---|---|
| RPO (max data loss) | production: **<= 1 h** with Render point-in-time recovery; **<= 24 h** worst case from our own nightly dump | Render managed Postgres PITR + `vaka-backup` cron at 02:15 UTC |
| RTO (time to serve again) | **<= 2 h** from decision to restore | managed restore (minutes to ~1 h by size) or `pg_restore` of the latest dump into a fresh database, then repoint `DATABASE_URL` |
| Staging | no targets (rebuildable from a production-shaped dump or seed) | |

These are targets for a one-person/small team on single-instance infrastructure, not guarantees. The restore drill below is
what turns them into measured numbers: write the measured restore time into the drill log.

## Two independent safety nets

| | Render Postgres backups | Our own dumps (`Dockerfile.backup`) |
|---|---|---|
| What | managed backups / point-in-time recovery of `vaka-db` (paid plans; retention window depends on the workspace plan, 3-7 days at the time of writing - **confirm in Dashboard -> vaka-db -> Recovery**) | `pg_dump --format=custom` nightly, stored in an S3-compatible bucket outside Render |
| Protects against | bad migration, accidental `DELETE`, corruption, instance loss (restore to a timestamp) | losing the Render account/region/workspace, expired retention, a mistake noticed after weeks, vendor lock-in |
| Retention | Render's window | 14 daily + 8 weekly (`BACKUP_KEEP_DAILY`, `BACKUP_KEEP_WEEKLY`) |
| Restore | creates a **new** database instance; you repoint the app | `restore_test.sh <file>` style `pg_restore` into any Postgres >= 16 |
| Verified how | Render's responsibility; test via the drill | `vaka-restore-test` cron every Monday restores the latest dump into a scratch DB and checks it |

Neither replaces the other. The bucket must live in a **different provider/account** than Render, with versioning or object
lock if available, and the backup credentials must only be able to write (and list/delete under `vaka/<env>/`) - not to
manage the bucket. Use read-only credentials for the restore-test cron where the provider allows it.

## What the scripts guarantee

`backend/scripts/backup.sh`: `pg_dump -Fc -Z6` -> `pg_restore --list` (archive readable) -> size sanity -> sha256 + row-count sidecar ->
upload to `<prefix>/daily/` (and `<prefix>/weekly/` on Sundays) -> prune to 14 daily / 8 weekly. Any failure exits non-zero (Render marks
the cron run failed and notifies) and posts to `ALERT_WEBHOOK_URL`. No credential or DSN is echoed.

`backend/scripts/restore_test.sh`: downloads the newest daily dump (fails if older than 36 h: the backup job stopped), verifies sha256,
creates `vaka_restore_test_<timestamp>_<n>` on the same server, `pg_restore --exit-on-error`, then checks `alembic_version`,
row counts of `users`/`case_sessions`/`case_reports` (and the recorded dump-time counts: a table that was non-empty must not restore
empty), no unvalidated constraints, no orphan rows, expected indexes; prints duration; drops the scratch database on exit
(success or failure). It never connects to the live database for anything except `CREATE/DROP DATABASE` of the scratch name.
If the app role lacks `CREATEDB` on the managed instance, set `RESTORE_ADMIN_URL` on the cron job to a throw-away Postgres.

Local proof (2026-10-20, dev Postgres 16, throw-away DB with 25 users / 100 sessions / 52 reports, images built from `Dockerfile.backup`):
backup OK in 1 s (28 KB), restore test OK: `schema=0001 ... rows: users=25 case_sessions=100 case_reports=52`; retention test with
5 fake old dailies and 3 fake weeklies pruned to 3/2 as configured; a wrong password and a truncated dump both exited 1 and posted the alert.

## Quarterly restore drill (checklist)

Owner: ops. Time-box: 1 hour. Log the result (date, dump used, restore duration, row counts, problems) in your ops notes.

- [ ] Confirm last night's `vaka-backup` run is green and the newest object in `vaka/production/daily/` is < 24 h old; at least 8 weekly files exist.
- [ ] Trigger `vaka-restore-test` manually (Render -> cron job -> *Trigger Run*); it must exit 0. Record `restore=` and `total=` seconds.
- [ ] **Full-fidelity drill:** download a weekly dump, `pg_restore` it into a local/throw-away Postgres 16, run the app against it
      (`DATABASE_URL=... AUTO_MIGRATE=false uvicorn server:app`), log in as an admin and open a real report. Record how long it took end to end (this is the RTO measurement).
- [ ] Render PITR: restore the production DB to a new instance at a timestamp 1 hour ago (Dashboard -> vaka-db -> Recovery), compare row counts, **delete the new instance** afterwards (it bills).
- [ ] Check an alert path: set a wrong `AWS_SECRET_ACCESS_KEY` on `vaka-staging-backup`, trigger a run, confirm both the Render failure notification and the webhook message arrive; restore the key.
- [ ] Verify bucket access separation: the backup key cannot delete other prefixes or change bucket settings.
- [ ] Review retention vs. the privacy promise (PRIVACY_AND_RETENTION.md) and update RPO/RTO numbers with what was measured.

## Data-loss plan

Triage first (5 minutes): what was lost, since when, is it still happening? Stop the bleeding before restoring (roll back the
release, disable the faulty job, or scale the web service to 0 to stop writes).

| Situation | Action |
|---|---|
| Bad deploy/migration corrupted or deleted rows (noticed within Render's PITR window) | Render PITR to a **new** database at a timestamp just before the event. Compare. Either repoint `DATABASE_URL` to the new DB (fast, loses writes since the event) or copy the missing rows back with `INSERT ... SELECT` from the restored DB (keeps newer writes). |
| Noticed later than the PITR window | Latest suitable dump from `vaka/production/daily|weekly/`. Restore into a **new** database (`createdb`, `pg_restore --no-owner --dbname`), then surgical row copy as above, or full cutover if the loss is total. |
| Whole database gone | Create a new Postgres (same plan/region), `pg_restore` the newest dump, `alembic upgrade head` (no-op if current), update `DATABASE_URL` on the service (Render's `fromDatabase` link is automatic if the DB keeps its blueprint name), redeploy, check `/api/ready`. Data since the dump (<= 24 h) is lost; sessions/jobs are the only high-churn tables and users can restart a case. |
| Render account/region unavailable | Stand up the Docker image elsewhere (it is plain Docker + Postgres + optional Redis), restore the dump from the bucket, point DNS. Secrets: keep an offline copy of the inventory in SECURITY.md in your password manager. |
| Redis lost | Nothing to restore. Rate-limit windows reset, TTS cache is cold. |
| Bucket lost/compromised | Create a new bucket + keys, run `vaka-backup` immediately, rotate the old keys, check that no dump was exfiltrated (dumps contain emails and chat transcripts). |

After any restore: (1) re-apply account deletions requested since the backup date (see PRIVACY_AND_RETENTION.md, "Deleted users and backups"),
(2) invalidate sessions if compromise is suspected (`DELETE FROM auth_sessions`), (3) reconcile billing against iyzico
(`billing.reconcile_all()` / iyzico dashboard) because `subscriptions` may be behind, (4) write the post-mortem.
