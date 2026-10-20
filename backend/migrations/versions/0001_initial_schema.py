"""Initial schema: users, auth sessions, case sessions/reports, AI cases, jobs, usage, billing.

Policy: migrations are additive (expand/contract). Never DROP a table or column that holds
production data in the same release that stops using it - drop it in a later, reviewed migration.

Revision ID: 0001
Revises:
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UP = [
    """CREATE TABLE users (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        google_sub text NOT NULL UNIQUE,
        email text NOT NULL,
        email_verified boolean NOT NULL DEFAULT false,
        name text,
        picture text,
        role text NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
        created_at timestamptz NOT NULL DEFAULT now(),
        last_login_at timestamptz
    )""",
    "CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email))",
    """CREATE TABLE auth_sessions (
        token_hash text PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        created_at timestamptz NOT NULL DEFAULT now(),
        expires_at timestamptz NOT NULL,
        user_agent text
    )""",
    "CREATE INDEX auth_sessions_user_idx ON auth_sessions (user_id)",
    "CREATE INDEX auth_sessions_expiry_idx ON auth_sessions (expires_at)",
    """CREATE TABLE case_sessions (
        id uuid PRIMARY KEY,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        case_id text NOT NULL,
        lang text NOT NULL CHECK (lang IN ('tr', 'en')),
        ended boolean NOT NULL DEFAULT false,
        data jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX case_sessions_user_created_idx ON case_sessions (user_id, created_at DESC)",
    """CREATE TABLE case_reports (
        session_id uuid PRIMARY KEY REFERENCES case_sessions(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        case_id text NOT NULL,
        total integer NOT NULL,
        grade text NOT NULL,
        report jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX case_reports_user_idx ON case_reports (user_id, created_at DESC)",
    """CREATE TABLE ai_cases (
        case_id text PRIMARY KEY,
        topic text NOT NULL,
        created_by uuid REFERENCES users(id) ON DELETE CASCADE,
        data jsonb NOT NULL,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX ai_cases_owner_idx ON ai_cases (created_by, topic)",
    """CREATE TABLE jobs (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind text NOT NULL,
        status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
        idempotency_key text NOT NULL,
        payload jsonb NOT NULL DEFAULT '{}'::jsonb,
        result jsonb,
        error text,
        progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
        stage text,
        attempts integer NOT NULL DEFAULT 0,
        max_attempts integer NOT NULL DEFAULT 3,
        run_after timestamptz NOT NULL DEFAULT now(),
        locked_until timestamptz,
        created_at timestamptz NOT NULL DEFAULT now(),
        started_at timestamptz,
        finished_at timestamptz,
        UNIQUE (user_id, kind, idempotency_key)
    )""",
    "CREATE INDEX jobs_claim_idx ON jobs (run_after) WHERE status IN ('pending', 'processing')",
    "CREATE INDEX jobs_user_idx ON jobs (user_id, created_at DESC)",
    """CREATE TABLE llm_usage (
        id bigserial PRIMARY KEY,
        user_id uuid REFERENCES users(id) ON DELETE SET NULL,
        kind text NOT NULL,
        provider text NOT NULL,
        model text NOT NULL,
        input_tokens integer NOT NULL DEFAULT 0,
        output_tokens integer NOT NULL DEFAULT 0,
        chars integer NOT NULL DEFAULT 0,
        cost_usd numeric(12, 6) NOT NULL DEFAULT 0,
        latency_ms integer,
        ref text,
        created_at timestamptz NOT NULL DEFAULT now()
    )""",
    "CREATE INDEX llm_usage_user_time_idx ON llm_usage (user_id, created_at DESC)",
    "CREATE INDEX llm_usage_time_idx ON llm_usage (created_at)",
    """CREATE TABLE subscriptions (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        provider text NOT NULL DEFAULT 'iyzico',
        plan text NOT NULL CHECK (plan IN ('pro_monthly', 'pro_yearly')),
        status text NOT NULL CHECK (status IN ('pending', 'active', 'past_due', 'canceled', 'expired')),
        provider_customer_ref text,
        provider_subscription_ref text UNIQUE,
        current_period_end timestamptz,
        cancel_at_period_end boolean NOT NULL DEFAULT false,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )""",
    """CREATE TABLE payment_events (
        id bigserial PRIMARY KEY,
        provider text NOT NULL,
        event_id text NOT NULL,
        event_type text NOT NULL,
        payload jsonb NOT NULL,
        received_at timestamptz NOT NULL DEFAULT now(),
        processed_at timestamptz,
        UNIQUE (provider, event_id)
    )""",
    # carry over AI-generated cases created before accounts existed (shared, no owner)
    """DO $$
    BEGIN
        IF to_regclass('public.generated_cases') IS NOT NULL THEN
            INSERT INTO ai_cases (case_id, topic, created_by, data)
            SELECT case_id, COALESCE(data->>'topic', 'endodontics'), NULL, data
            FROM generated_cases
            ON CONFLICT DO NOTHING;
        END IF;
    END $$""",
]


def upgrade() -> None:
    for stmt in UP:
        op.execute(stmt)


def downgrade() -> None:
    raise RuntimeError("Irreversible by design: restore from backup instead of dropping production tables.")
