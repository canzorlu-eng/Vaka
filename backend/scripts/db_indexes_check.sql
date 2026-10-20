-- Query-plan review for the hot queries of repo.py / jobs.py / usage.py / plans.py.
--
-- Run it against a COPY of production data (e.g. a database restored by restore_test.sh) or a seeded dev database,
-- never against production: the DELETE/UPDATE statements are executed by EXPLAIN ANALYZE (they are rolled back,
-- but they still take row locks and generate WAL).
--
--   psql "$SCRATCH_DATABASE_URL" -X -f backend/scripts/db_indexes_check.sql
--
-- Sections: 1 query plans (look for Seq Scan on big tables)   2 index inventory/usage   3 unindexed foreign keys
-- Findings and the proposed (NOT applied) migration are in docs/ARCHITECTURE.md ("Database indexes").
\set ON_ERROR_STOP on
\pset pager off
\timing off

-- A heavy user (most sessions) and one of their session ids, so the plans reflect the worst realistic case.
SELECT user_id AS uid FROM case_sessions GROUP BY user_id ORDER BY count(*) DESC LIMIT 1 \gset
SELECT id AS sid FROM case_sessions WHERE user_id = :'uid' LIMIT 1 \gset
SELECT (SELECT count(*) FROM case_sessions) AS case_sessions_rows, (SELECT count(*) FROM jobs) AS jobs_rows,
       (SELECT count(*) FROM llm_usage) AS llm_usage_rows, (SELECT count(*) FROM auth_sessions) AS auth_rows;

\echo '=== 1.1 repo.list_sessions (keyset page, LEFT JOIN case_reports)'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT s.id, s.case_id, s.lang, s.ended, s.created_at, r.total, r.grade
FROM case_sessions s LEFT JOIN case_reports r ON r.session_id = s.id
WHERE s.user_id = :'uid' AND (NULL::timestamptz IS NULL OR s.created_at < NULL::timestamptz)
ORDER BY s.created_at DESC LIMIT 20;

\echo '=== 1.2 repo.get_session (id + user_id)'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT data FROM case_sessions WHERE id = :'sid' AND user_id = :'uid';

\echo '=== 1.3 repo.count_sessions_this_month'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT count(*) FROM case_sessions WHERE user_id = :'uid' AND created_at >= date_trunc('month', now());

\echo '=== 1.4 repo.user_for_token (every authenticated request)'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT u.id FROM auth_sessions s JOIN users u ON u.id = s.user_id
WHERE s.token_hash = md5('42') AND s.expires_at > now();

\echo '=== 1.5 jobs._claim (polled by each worker every second)'
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
UPDATE jobs SET status = 'processing', started_at = COALESCE(started_at, now()), attempts = attempts + 1,
       locked_until = now() + (210 * interval '1 second')
WHERE id = (SELECT id FROM jobs
            WHERE run_after <= now() AND (status = 'pending' OR (status = 'processing' AND locked_until < now()))
            ORDER BY run_after LIMIT 1 FOR UPDATE SKIP LOCKED)
RETURNING id;
ROLLBACK;

\echo '=== 1.6 jobs: idempotency lookup / generations_this_month (plans.py)'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT count(*) FROM jobs WHERE user_id = :'uid' AND kind = 'case_generation' AND status <> 'failed'
  AND created_at >= date_trunc('month', now());

\echo '=== 1.7 plans.plan_name_for (subscriptions by user)'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT 1 FROM subscriptions WHERE user_id = :'uid'
  AND (status = 'active' OR (status IN ('canceled', 'past_due') AND current_period_end > now()));

\echo '=== 1.8 usage.user_spend_24h (before every LLM call)'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE user_id = :'uid' AND created_at > now() - interval '24 hours';

\echo '=== 1.9 usage.global_spend_today (maintenance loop, every 5 min)'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE created_at >= date_trunc('day', now());

\echo '=== 1.10 maintenance: DELETE expired auth_sessions'
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON) DELETE FROM auth_sessions WHERE expires_at < now();
ROLLBACK;

\echo '=== 1.11 maintenance: DELETE old finished jobs (retention 30 d)'
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON) DELETE FROM jobs WHERE finished_at < now() - (30 * interval '1 day');
ROLLBACK;

\echo '=== 1.12 maintenance: DELETE old case_sessions (retention 180 d)'
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON) DELETE FROM case_sessions WHERE created_at < now() - (180 * interval '1 day');
ROLLBACK;

\echo '=== 1.13 maintenance: mark abandoned jobs'
BEGIN;
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
UPDATE jobs SET status = 'failed', error = 'abandoned', finished_at = now()
WHERE status = 'processing' AND locked_until < now() AND attempts >= max_attempts;
ROLLBACK;

\echo '=== 1.14 repo.list_ai_cases / get_ai_case'
EXPLAIN (ANALYZE, BUFFERS, COSTS OFF, SUMMARY ON)
SELECT data FROM ai_cases WHERE (NULL::text IS NULL OR topic = NULL::text) AND (created_by IS NULL OR created_by = :'uid')
ORDER BY created_at DESC LIMIT 100;

\echo '=== 2. index inventory with usage since last stats reset (idx_scan = 0 on a busy DB => candidate to drop)'
SELECT s.relname AS "table", s.indexrelname AS "index", s.idx_scan, pg_size_pretty(pg_relation_size(s.indexrelid)) AS size
FROM pg_stat_user_indexes s ORDER BY s.relname, s.indexrelname;

\echo '=== 3. foreign keys WITHOUT a supporting index on the referencing column (slow cascades/deletes)'
SELECT c.conrelid::regclass AS "table", a.attname AS column, c.confrelid::regclass AS references
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
WHERE c.contype = 'f' AND array_length(c.conkey, 1) = 1
  AND NOT EXISTS (SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid AND i.indkey[0] = c.conkey[1])
ORDER BY 1, 2;
