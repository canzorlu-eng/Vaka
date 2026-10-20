# Vaka

Diş hekimliği sanal hasta simülasyonu: FastAPI + PostgreSQL + Redis + React. Render üzerinde Docker olarak çalışır
(production + staging).

## Hızlı başlangıç (yerel geliştirme)

1. Servisleri başlat (Postgres `localhost:55432` vaka/vaka, Redis `localhost:56379`):
   ```bash
   docker compose -f docker-compose.dev.yml up -d
   ```
2. Backend:
   ```bash
   cd backend
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements-dev.txt
   cp .env.example .env     # DATABASE_URL, REDIS_URL, SECRET_KEY (>=32 karakter), GOOGLE_*, GEMINI_*, OPENAI_* değerlerini doldur
   AUTO_MIGRATE=true uvicorn server:app --reload --port 8001   # tablolar Alembic ile oluşur
   ```
3. Frontend (`frontend/.env` içinde `REACT_APP_BACKEND_URL`):
   ```bash
   cd frontend
   npm ci --legacy-peer-deps && npm install --no-save --legacy-peer-deps ajv@8   # ajv: bkz. docs/RUNBOOK.md, "Requested app changes"
   npm start
   ```
4. Testler: `cd backend && pytest -q` (dev Postgres'te geçici `vaka_test` veritabanı kullanır).

API anahtarları yoksa uygulama çalışır; AI hasta yanıtı, vaka üretimi ve TTS devre dışı kalır.

## Docker

```bash
docker build -t vaka .          # Node ile frontend build + FastAPI imajı (non-root, HEALTHCHECK /api/health)
docker build -f Dockerfile.backup -t vaka-backup .   # nightly pg_dump / restore drill imajı
```

## Dokümantasyon (`docs/`)

| Doküman | İçerik |
|---|---|
| [SETUP_GUIDE.md](docs/SETUP_GUIDE.md) | İlk kurulum: Google OAuth, Render Blueprint, R2/B2 yedek bucket, iyzico, Gemini/OpenAI limitleri |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Bileşenler, istek akışı, veri modeli, job'lar, tüm env değişkenleri, index analizi, yük testi |
| [RUNBOOK.md](docs/RUNBOOK.md) | Deploy, staging -> production, rollback (expand/contract), domain/HTTPS/CORS, alarm, olay kontrol listesi |
| [DISASTER_RECOVERY.md](docs/DISASTER_RECOVERY.md) | RPO/RTO, Render yedekleri vs. kendi dump'larımız, üç aylık restore tatbikatı, veri kaybı planı |
| [SECURITY.md](docs/SECURITY.md) | Ortam ayrımı, secret envanteri ve rotasyon, sızıntı durumunda yapılacaklar |
| [PRIVACY_AND_RETENTION.md](docs/PRIVACY_AND_RETENTION.md) | Veri envanteri, saklama süreleri, silme/dışa aktarma, işlemciler |

## Operasyon dosyaları

- `render.yaml`: production (`main`) ve staging (`staging`) için ayrı Postgres, Key Value (Redis), web servisi ve cron job'lar.
- `.github/workflows/ci.yml`: ruff, pytest (Postgres 16 + Redis 7), alembic, pip-audit, frontend build, docker build, gitleaks, **deploy gate**.
- `.github/workflows/staging-smoke.yml`: verilen URL için health/ready/SPA smoke testi.
- `backend/scripts/`: `backup.sh`, `restore_test.sh`, `loadtest.py`, `db_indexes_check.sql`, `iyzico_setup.py`.
