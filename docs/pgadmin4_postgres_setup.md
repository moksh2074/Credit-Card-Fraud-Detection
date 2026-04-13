# pgAdmin4 + PostgreSQL Setup (Local)

This guide connects your project backend to a local PostgreSQL server managed through pgAdmin4.

## 1) Prerequisites

1. Install PostgreSQL server locally (pgAdmin alone is not a database server).
2. Ensure PostgreSQL service is running.
3. Open pgAdmin4.

## 2) Register Local Server in pgAdmin4

1. Right-click `Servers` -> `Register` -> `Server...`
2. In `General` tab:
   - Name: `Local PostgreSQL`
3. In `Connection` tab:
   - Host name/address: `localhost`
   - Port: `5432`
   - Maintenance database: `postgres`
   - Username: `postgres`
   - Password: `<your_postgres_password>`
4. Save.

## 3) Create App Database + User

Open Query Tool on the `postgres` database and run:

```sql
CREATE DATABASE transactions_db;
```

Then run:

```sql
DO $$
BEGIN
   IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'fraud_app') THEN
      CREATE ROLE fraud_app LOGIN PASSWORD 'fraud_app_123';
   END IF;
END $$;
```

Grant privileges:

```sql
GRANT ALL PRIVILEGES ON DATABASE transactions_db TO fraud_app;
```

Connect Query Tool to `transactions_db`, then run:

```sql
GRANT USAGE, CREATE ON SCHEMA public TO fraud_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO fraud_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO fraud_app;
```

## 4) Configure Backend Environment

Create/update `backend/.env`:

```env
DATABASE_URL=postgresql://fraud_app:fraud_app_123@localhost:5432/transactions_db
```

The app now auto-normalizes this to asyncpg internally, so `postgresql://` works.

## 5) Start Backend

From project root:

```powershell
uvicorn main:app --reload --port 8000
```

On startup, tables are auto-created.

## 6) Verify Data Writes in pgAdmin

In pgAdmin, open Query Tool on `transactions_db`:

```sql
SELECT COUNT(*) FROM transactions;
SELECT COUNT(*) FROM fraud_alerts;
SELECT id, created_at, amount, risk_level, predicted_class, data_source
FROM transactions
ORDER BY created_at DESC
LIMIT 20;
```

When simulation runs from frontend generator, rows should appear here.

## 7) Troubleshooting

1. Connection refused:
   - PostgreSQL service is not running.
   - Wrong host/port.
2. Password/auth failed:
   - Wrong DB user/password in `backend/.env`.
3. Tables not created:
   - Check backend logs for startup errors.
4. Data not appearing:
   - Confirm backend started with correct `DATABASE_URL`.
   - Check API health: `GET http://127.0.0.1:8000/health`.
