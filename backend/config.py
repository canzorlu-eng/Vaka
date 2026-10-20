"""Single source of truth for configuration. Every value comes from the environment (.env in dev,
Render env vars in staging/production). Secrets never reach the frontend bundle."""
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(_env(name, str(default)))


def _bool(name: str, default: bool) -> bool:
    return _env(name, "true" if default else "false").lower() in ("1", "true", "yes", "on")


def _list(name: str) -> List[str]:
    return [x.strip() for x in _env(name).split(",") if x.strip()]


@dataclass(frozen=True)
class Settings:
    # --- runtime ---
    env: str = field(default_factory=lambda: _env("APP_ENV", "development"))  # development|staging|production
    public_base_url: str = field(default_factory=lambda: _env("PUBLIC_BASE_URL", "http://localhost:8001").rstrip("/"))
    cors_origins: List[str] = field(default_factory=lambda: _list("CORS_ORIGINS"))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))
    auto_migrate: bool = field(default_factory=lambda: _bool("AUTO_MIGRATE", _env("APP_ENV", "development") == "development"))
    # --- datastores ---
    database_url: str = field(default_factory=lambda: _env("DATABASE_URL"))
    db_pool_max: int = field(default_factory=lambda: _int("DB_POOL_MAX", 10))
    db_command_timeout: int = field(default_factory=lambda: _int("DB_COMMAND_TIMEOUT", 30))
    redis_url: str = field(default_factory=lambda: _env("REDIS_URL"))
    # --- auth ---
    secret_key: str = field(default_factory=lambda: _env("SECRET_KEY"))
    google_client_id: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_ID"))
    google_client_secret: str = field(default_factory=lambda: _env("GOOGLE_CLIENT_SECRET"))
    admin_emails: List[str] = field(default_factory=lambda: [e.lower() for e in _list("ADMIN_EMAILS")])
    session_ttl_days: int = field(default_factory=lambda: _int("SESSION_TTL_DAYS", 30))
    # --- AI providers ---
    gemini_api_key: str = field(default_factory=lambda: _env("GEMINI_API_KEY"))
    gemini_model: str = field(default_factory=lambda: _env("GEMINI_MODEL", "gemini-3.5-flash-lite"))
    # Optional per-task overrides (empty = use GEMINI_MODEL): a stronger model for rare, quality-critical work
    gemini_model_generation: str = field(default_factory=lambda: _env("GEMINI_MODEL_GENERATION"))
    gemini_model_scoring: str = field(default_factory=lambda: _env("GEMINI_MODEL_SCORING"))
    gemini_thinking_budget: int = field(default_factory=lambda: _int("GEMINI_THINKING_BUDGET", -1))  # -1 = model default
    openai_api_key: str = field(default_factory=lambda: _env("OPENAI_API_KEY"))
    tts_model: str = field(default_factory=lambda: _env("OPENAI_TTS_MODEL", "tts-1"))
    tts_voice: str = field(default_factory=lambda: _env("OPENAI_TTS_VOICE", "coral"))
    llm_timeout_ms: int = field(default_factory=lambda: _int("LLM_TIMEOUT_MS", 45_000))
    llm_max_concurrency: int = field(default_factory=lambda: _int("LLM_MAX_CONCURRENCY", 8))
    # --- price table (USD) used for cost tracking; verified against provider pricing pages on 2026-10-20 ---
    # Fallback for models missing from llm.MODEL_PRICES (USD per 1M tokens; output includes thinking tokens).
    price_gemini_in_per_m: float = field(default_factory=lambda: _float("PRICE_GEMINI_IN_PER_M", 0.75))
    price_gemini_out_per_m: float = field(default_factory=lambda: _float("PRICE_GEMINI_OUT_PER_M", 3.75))
    price_tts_per_m_chars: float = field(default_factory=lambda: _float("PRICE_TTS_PER_M_CHARS", 15.0))
    # --- cost guard rails ---
    user_daily_cost_cap_free: float = field(default_factory=lambda: _float("USER_DAILY_COST_CAP_FREE_USD", 0.05))
    user_daily_cost_cap_pro: float = field(default_factory=lambda: _float("USER_DAILY_COST_CAP_PRO_USD", 1.50))
    # Month-to-date caps bound worst-case abuse well below plan revenue ($9/mo); sized from scripts/cost_probe.py
    user_monthly_cost_cap_free: float = field(default_factory=lambda: _float("USER_MONTHLY_COST_CAP_FREE_USD", 0.15))
    user_monthly_cost_cap_pro: float = field(default_factory=lambda: _float("USER_MONTHLY_COST_CAP_PRO_USD", 4.0))
    max_messages_per_session: int = field(default_factory=lambda: _int("MAX_MESSAGES_PER_SESSION", 40))
    global_daily_cost_alert: float = field(default_factory=lambda: _float("GLOBAL_DAILY_COST_ALERT_USD", 20.0))
    alert_webhook_url: str = field(default_factory=lambda: _env("ALERT_WEBHOOK_URL"))  # Slack/Discord-compatible
    # --- limits ---
    max_body_bytes: int = field(default_factory=lambda: _int("MAX_BODY_BYTES", 32_768))
    max_chat_chars: int = field(default_factory=lambda: _int("MAX_CHAT_CHARS", 600))
    global_ip_limit_per_min: int = field(default_factory=lambda: _int("GLOBAL_IP_LIMIT_PER_MIN", 300))
    # --- jobs ---
    job_workers: int = field(default_factory=lambda: _int("JOB_WORKERS", 2))
    job_timeout_s: int = field(default_factory=lambda: _int("JOB_TIMEOUT_S", 180))
    job_max_attempts: int = field(default_factory=lambda: _int("JOB_MAX_ATTEMPTS", 3))
    # --- retention (days) ---
    retention_sessions_days: int = field(default_factory=lambda: _int("RETENTION_SESSIONS_DAYS", 180))
    retention_jobs_days: int = field(default_factory=lambda: _int("RETENTION_JOBS_DAYS", 30))
    # --- payments (iyzico) ---
    iyzico_api_key: str = field(default_factory=lambda: _env("IYZICO_API_KEY"))
    iyzico_secret_key: str = field(default_factory=lambda: _env("IYZICO_SECRET_KEY"))
    iyzico_base_url: str = field(default_factory=lambda: _env("IYZICO_BASE_URL", "https://sandbox-api.iyzipay.com"))
    iyzico_merchant_id: str = field(default_factory=lambda: _env("IYZICO_MERCHANT_ID"))
    iyzico_webhook_secret: str = field(default_factory=lambda: _env("IYZICO_WEBHOOK_SECRET"))
    # Plan reference codes created by scripts/iyzico_setup.py (one per interval x currency).
    iyzico_plan_monthly_usd: str = field(default_factory=lambda: _env("IYZICO_PLAN_MONTHLY_USD"))
    iyzico_plan_yearly_usd: str = field(default_factory=lambda: _env("IYZICO_PLAN_YEARLY_USD"))
    iyzico_plan_monthly_try: str = field(default_factory=lambda: _env("IYZICO_PLAN_MONTHLY_TRY"))
    iyzico_plan_yearly_try: str = field(default_factory=lambda: _env("IYZICO_PLAN_YEARLY_TRY"))
    # Display/charge amounts. USD is the list price; TRY is charged to Turkish-issued cards (iyzico limitation).
    price_monthly_usd: float = field(default_factory=lambda: _float("PRICE_MONTHLY_USD", 9.0))
    price_yearly_usd: float = field(default_factory=lambda: _float("PRICE_YEARLY_USD", 90.0))
    price_monthly_try: float = field(default_factory=lambda: _float("PRICE_MONTHLY_TRY", 399.0))
    price_yearly_try: float = field(default_factory=lambda: _float("PRICE_YEARLY_TRY", 3990.0))

    @property
    def is_prod(self) -> bool:
        return self.env == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.public_base_url.startswith("https://")

    @property
    def allowed_origins(self) -> Tuple[str, ...]:
        return tuple({self.public_base_url, *self.cors_origins})

    def validate(self) -> None:
        """Fail fast on a mis-configured deployment."""
        missing = [n for n, v in (("DATABASE_URL", self.database_url), ("SECRET_KEY", self.secret_key)) if not v]
        if missing:
            raise RuntimeError(f"Missing required settings: {', '.join(missing)}")
        if len(self.secret_key) < 32:
            raise RuntimeError("SECRET_KEY must be at least 32 characters")
        if self.is_prod and not self.public_base_url.startswith("https://"):
            raise RuntimeError("PUBLIC_BASE_URL must be https in production")
        if self.is_prod and not self.redis_url:
            raise RuntimeError("REDIS_URL is required in production (shared rate limits and cache)")


settings = Settings()
