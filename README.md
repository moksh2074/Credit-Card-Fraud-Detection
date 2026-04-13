# Credit Card Fraud Detection Platform

Real-time fraud detection platform with:
- Synthetic transaction generation
- ML scoring and alerting
- Live dashboard/analytics via SSE
- Transaction and alert operations UI
- Local fraud log sink + optional AWS S3 archival

## 1. System Overview

This project is a full-stack fraud detection workflow:

1. The **Synthetic Generator** creates transaction payloads.
2. Payloads are ingested at `POST /api/v1/transactions/ingest`.
3. Backend computes engineered fraud features (velocity, geo behavior, device context).
4. ML scorer returns `fraud_score`, `risk_level`, `predicted_class`, SHAP features, and latency.
5. Transaction is persisted to DB (`transactions` table).
6. If flagged/high risk, alert is created in `fraud_alerts`.
7. SSE broadcasts `transaction_ingested` and related events.
8. Frontend pages refresh via polling + SSE triggers.
9. Flagged-model logs are always written locally (`fraud_logs.json`) and optionally archived to S3.

## 2. Core Tech Stack

- Frontend: React 18 + Vite + Tailwind + Recharts + Zustand
- Backend: FastAPI + SQLAlchemy async + Pydantic + Uvicorn
- DB: PostgreSQL (primary), SQLite fallback runtime support
- Streaming: Server-Sent Events (SSE)
- ML: scikit-learn + SHAP
- Optional: Redis/Celery, AWS S3 archival, IBM COS compatibility

## 3. Project Structure

- `backend/main.py`: FastAPI app bootstrap, router registration, startup lifecycle
- `backend/app/api/routes/`: all API route modules
- `backend/app/db/models/`: ORM models (`transactions`, `fraud_alerts`, users)
- `backend/app/generator/synthetic/generator.py`: synthetic source of transaction flow
- `backend/app/ml/`: feature engineering + scoring
- `backend/app/services/logging/log_builder.py`: local + optional S3/COS log dispatch
- `frontend/src/pages/`: route-level pages
- `frontend/src/components/`: UI components/charts/tables
- `frontend/src/services/`: API service wrappers

## 4. Data Model Summary

### `transactions` table

Important fields:
- Identity: `id`, `card_id_hash`, `merchant_id`, `merchant_name`, `mcc`
- Transaction: `amount`, `currency`, `channel`, `created_at`, `data_source`
- Device/Geo: `device_id`, `device_type`, `is_new_device`, `ip_address`, `geo_*`
- Engineered: `velocity_1h`, `velocity_24h`, `geo_distance_km`, `implied_speed_kmh`, `impossible_travel_flag`, `mcc_risk_class`
- ML Output: `fraud_score`, `risk_level`, `predicted_class`, `shap_features`, `model_version`, `inference_latency_ms`
- Processing: `processing_status`

### `fraud_alerts` table

Important fields:
- `transaction_id`, `card_id_hash`, `severity`, `status`, `outcome`, `rule_triggers`, timestamps

## 5. Live Workflow Details

### 5.1 Generator -> Ingestion

- Generator creates realistic traffic with configurable:
  - TPS (`tps`)
  - Fraud injection rate (`fraud_injection_rate`)
  - Scenario mix (`velocity_burst`, `impossible_travel`, `card_testing`, `high_value_cnp`, `new_device_fraud`)
- Each payload is posted to:
  - `POST /api/v1/transactions/ingest`

### 5.2 Scoring + Alerting

On ingest:
1. Payload is normalized.
2. Feature vectors are engineered from recent history.
3. ML scoring happens.
4. Transaction row is stored.
5. Alert row is created when flagged/high-risk conditions match.

### 5.3 Streaming

- Backend SSE endpoint: `GET /api/v1/stream/transactions`
- Frontend pages (Dashboard, Transactions, Alerts, Analytics, Generator) react to stream events.

### 5.4 Dashboard/Analytics Refresh Reliability

Current behavior is resilient:
- Polling refresh (periodic)
- SSE-triggered refresh (event-based)
- Local snapshot caching in frontend (`localStorage`) to avoid chart/table wipeouts on transient API failures
- Failed refresh now preserves last known good state instead of clearing data

## 6. APIs (Main)

### Auth
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`

### Transactions
- `POST /api/v1/transactions/ingest`
- `GET /api/v1/transactions`
- `GET /api/v1/transactions/export`
- `GET /api/v1/transactions/{id}`
- `GET /api/v1/transactions/customer-verification`

### Alerts
- `GET /api/v1/alerts`
- `PATCH /api/v1/alerts/{id}/status`

### Analytics
- `GET /api/v1/analytics/fraud-summary`
- `GET /api/v1/analytics/fraud-rate-trend`
- `GET /api/v1/analytics/risk-distribution`
- `GET /api/v1/analytics/device-channel`
- `GET /api/v1/analytics/merchant-category`
- `GET /api/v1/analytics/time-heatmap`
- `GET /api/v1/analytics/model-performance`

### Generator
- `POST /api/v1/generator/start`
- `POST /api/v1/generator/stop`
- `GET /api/v1/generator/status`
- `PATCH /api/v1/generator/config`

## 7. Local Setup (Exact Steps)

### 7.1 Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL running locally
- (Optional) Redis if using Celery-related flows

### 7.2 Backend setup

From repo root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

Create/update `backend/.env`:

```env
DATABASE_URL=postgresql://fraud_app:fraud_app_123@localhost:5433/transactions_db
SECRET_KEY=replace-this-with-a-secure-secret-key-in-production
JWT_ALGORITHM=HS256
JWT_ACCESS_TTL_MINUTES=15
AWS_S3_ENABLED=false
AWS_REGION=ap-south-1
AWS_S3_BUCKET=
AWS_S3_PREFIX=fraud-logs/
AWS_S3_OBJECT_EXTENSION=.txt
AWS_S3_ENDPOINT_URL=
AWS_S3_DISABLE_PROXY=true
AWS_S3_PENDING_PATH=
AWS_S3_FLUSH_EVERY_N_RECORDS=25
AWS_S3_RECORDS_PER_OBJECT=200
AWS_S3_MAX_OBJECTS_PER_FLUSH=3
AWS_S3_FLUSH_MIN_INTERVAL_SEC=5
```

Start backend (either option works):

```powershell
cd ..
uvicorn main:app --reload --port 8000
```

or

```powershell
cd backend
uvicorn main:app --reload --port 8000
```

Health check:

- `GET http://127.0.0.1:8000/health`

### 7.3 Frontend setup

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open:
- `http://localhost:3000` (or Vite default shown in terminal)

### 7.4 Create/login user

Register once:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"admin@example.com\",\"password\":\"Admin@1234\",\"role\":\"admin\",\"org_id\":\"org_001\"}"
```

Then login through frontend at `/login`.

### 7.5 Start simulation

Use Generator tab in UI:
- Set TPS and fraud rate
- Start simulation
- Verify live updates on Dashboard, Transactions, Alerts, Analytics

## 8. Optional S3 Archival for Flagged Logs

When enabled:
- Local sink always: `backend/app/wazuh/forwarder/fraud_logs.json`
- Retry queue (if S3 unavailable): `backend/runtime/s3_pending_logs.ndjson`
- Sequence state: `backend/runtime/s3_sequence_counter.txt`
- S3 object prefix: `fraud-logs/date=YYYY-MM-DD/hour=HH/seq_<start>_<end>.txt`
- File content format: text file where each line is a JSON object (field-value pairs)

S3 deletion/recreation does not break main pipeline; backlog queues locally and retries.

## 9. Docker Compose Option

From repo root:

```powershell
docker compose up --build
```

Services in `docker-compose.yml`:
- `postgres`
- `redis`
- `backend`
- `celery_worker`
- `frontend`

## 10. Troubleshooting

### Dashboard/Analytics look empty

1. Confirm backend is up (`/health`).
2. Confirm generator is producing transactions.
3. Confirm DB has rows in `transactions`.
4. Check browser console for API errors.
5. SSE endpoint check: `GET /api/v1/stream/transactions`

### Login unauthorized

1. Ensure user exists via `/auth/register`.
2. Ensure email normalization matches (`lowercase`).
3. Check backend logs for auth errors.

### S3 has no objects

1. Ensure `AWS_S3_ENABLED=true`.
2. Ensure credentials are available in same process running backend.
3. Check local queue file `backend/runtime/s3_pending_logs.ndjson`.
4. If queue grows, S3 auth/permissions are failing.

## 11. Notes

- Synthetic generator is the internal source used for live testing workflows.
- Startup loads persisted model artifact once; no retraining on every boot.
- Frontend analytics requests are `synthetic_only=true` to focus on generated live streams.
