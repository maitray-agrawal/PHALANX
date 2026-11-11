# Neon Database Manual Setup for PHALANX

**Date:** 2026-11-10  
**Context:** Neon serverless PostgreSQL cannot run superuser scripts like `scripts/init_db.sh`.  
**Security:** This file contains **NO passwords or secrets**. Replace placeholders when running in the console.

---

## Why `scripts/init_db.sh` Cannot Run on Neon

In a local Docker setup, PostgreSQL runs with a superuser (`postgres`) capable of:
1. `CREATE ROLE phalanx_app WITH LOGIN`
2. `ALTER ROLE phalanx_app WITH PASSWORD '...'`
3. Setting `DEFAULT PRIVILEGES` across the database.

Neon does not provide a PostgreSQL `superuser` role; your admin account is `neondb_owner` (a member of `cloud_admin`).

## Setup Steps in Neon Web Console

### Option A: Use the Default Neon Database & Owner with Direct Connection (Recommended)

Neon provisions a default database `neondb` and role `neondb_owner`.
We **recommend using the DIRECT connection string** (the hostname without `-pooler`).
PHALANX uses SQLAlchemy connection pooling with row-level locking (`SELECT ... FOR UPDATE`),
Alembic migration DDL, and transaction-scoped sessions. Direct connections ensure full
PostgreSQL feature compatibility without PgBouncer transaction-pooling limitations.

Your connection string in Render environment variables (Direct Connection):
```
DATABASE_URL=postgresql+psycopg://neondb_owner:<YOUR_NEON_PASSWORD>@ep-example.us-east-2.aws.neon.tech/neondb?sslmode=require
```

> **Note on Pooled Connection String (`-pooler`):** If you choose to use Neon's connection pooler (`ep-example-pooler`), PHALANX automatically sets psycopg `prepare_threshold=None` in engine `connect_args` to disable server-side prepared statements, combined with `pool_pre_ping=True` and `pool_recycle=240` to avoid broken transaction pooler sessions. However, the Direct connection remains the primary recommendation.

When PHALANX boots, `scripts/boot.py` runs `alembic upgrade head` and creates all required tables and immutability triggers automatically using this role.

---

### Option B: Dedicated `phalanx_app` Role (Least-Privilege Setup)

If you prefer a dedicated non-owner application role, run the following SQL commands in the **Neon SQL Editor** (Dashboard -> SQL Editor):

```sql
-- 1. Create the application role with a secure password (replace <APP_PASSWORD> with a high-entropy secret)
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'phalanx_app') THEN
    CREATE ROLE phalanx_app WITH LOGIN PASSWORD '<APP_PASSWORD>';
  END IF;
END
$$;

-- 2. Grant basic connection and schema privileges
GRANT CONNECT ON DATABASE neondb TO phalanx_app;
GRANT USAGE, CREATE ON SCHEMA public TO phalanx_app;

-- 3. Grant table and sequence permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO phalanx_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO phalanx_app;

-- 4. Ensure future tables created by migrations inherit permissions
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO phalanx_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO phalanx_app;
```

---

## Ledger Immutability Triggers on Neon

PHALANX protects the ledger table `ledger_events` using PostgreSQL row-level triggers (`trg_deny_ledger_mutation` via function `deny_ledger_mutation()`).

These triggers are installed automatically by `scripts/boot.py` via `install_ledger_triggers()` during startup. They do **not** require superuser privileges because the application role owns the table created by Alembic.

To manually verify or apply the immutability trigger in Neon SQL Editor:

```sql
CREATE OR REPLACE FUNCTION deny_ledger_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'ledger_events is append-only: updates and deletes are prohibited';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_deny_ledger_mutation ON ledger_events;
CREATE TRIGGER trg_deny_ledger_mutation
BEFORE UPDATE OR DELETE ON ledger_events
FOR EACH ROW EXECUTE FUNCTION deny_ledger_mutation();
```

---

## Neon Verification Checklist

- [ ] Direct connection hostname (`ep-...` without `-pooler`) is used in `DATABASE_URL` (recommended).
- [ ] `?sslmode=require` is explicitly present in `DATABASE_URL`.
- [ ] SQLAlchemy engine tuning verified: `pool_pre_ping=True`, `pool_recycle=240`, `connect_timeout=10` (and `prepare_threshold=None` if pooled).
- [ ] `boot.py` completes cleanly (`Alembic migrations successfully applied to head`).
- [ ] `trg_deny_ledger_mutation` trigger is active on `ledger_events`.

