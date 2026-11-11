# Neon Free Plan — Evidence Record

**URL:** https://neon.tech/docs/introduction/plans  
**Retrieved:** 2026-11-10 (via web search + official docs index)  
**Status:** REPORTED (search-indexed content; Neon updates plan limits frequently —
verify storage quota and project count on the live page before hardcoding)

---

## Storage

| Attribute | Value |
|---|---|
| Storage per project | ~0.5–1 GB (sources differ; verify on live page) |
| Point-in-time restore window | 24 hours |

## Compute / Scale-to-Zero

| Attribute | Value |
|---|---|
| Scale-to-zero after inactivity | **5 minutes** |
| Free compute allowance | 100 CU-hours per project per month |
| Max compute size (autoscale cap) | 2 CU (~2 vCPU / 8 GB RAM) |
| Data egress | 5 GB per project per month |

## Connection Limits

| Mode | Limit |
|---|---|
| Direct connections (at 0.25 CU) | ~112 max_connections (105 usable) |
| Pooled connections (PgBouncer) | Up to 10,000 concurrent clients |

**Recommendation for PHALANX:** Use Neon's **direct connection string**
(standard hostname without `-pooler`) in `DATABASE_URL`. PHALANX uses SQLAlchemy's
built-in client-side connection pooling (`pool_size=10, max_overflow=20`), which is
well within the ~112 direct connection limit. Direct connections fully support
`SELECT ... FOR UPDATE` row locks, transactional DDL during Alembic migrations,
and prepared statements without PgBouncer limitations.

> If a pooled URL is used (`-pooler`), PHALANX automatically sets psycopg
> `prepare_threshold=None` in engine `connect_args` to disable server-side prepared statements.

## SSL Requirement

SSL is **mandatory** on Neon. Unencrypted connections are rejected.

Required connection string parameter: `?sslmode=require`

```
DATABASE_URL=postgresql+psycopg://<user>:<password>@<host>/<db>?sslmode=require
```

PHALANX enforces this at startup via a Pydantic field validator in
`app/infrastructure/config.py` (`require_ssl_for_neon`): if `neon.tech` appears
in the DATABASE_URL but `sslmode` is absent, the app refuses to start.

## PostgreSQL Version

Neon supports PostgreSQL 14, 15, 16, 17, and 18. Version is chosen at project
creation; Neon manages minor releases automatically.

## Projects / Branches

| Attribute | Value |
|---|---|
| Projects per free account | Up to 10 (verify on live page) |
| Branches per project | Up to 10 |

## Default Region

Neon provisions on AWS infrastructure. Default region at project creation is
typically **us-east-2 (Ohio)**. Other available regions include US West,
EU (Frankfurt), and Asia Pacific.

## Why `scripts/init_db.sh` Cannot Run on Neon

`init_db.sh` requires superuser access to run `CREATE ROLE`, `ALTER ROLE WITH PASSWORD`,
`GRANT CONNECT ON DATABASE`, and `ALTER DEFAULT PRIVILEGES`. Neon does not grant
superuser access on free projects.

**Solution:** Neon's project owner role (`neondb_owner`) has sufficient privileges
to run the equivalent SQL manually in the Neon SQL console. See
`docs/evidence/neon-manual-setup.md` for the exact SQL to execute once.

## Notes for PHALANX

- Use the **direct** connection string (`<host>.neon.tech` without `-pooler`) in hosted environments.
- Alembic runs `alembic upgrade head` at boot via `scripts/boot.py` — this is
  the only schema migration path on Neon; `init_db.sh` is for local Docker only.
- The immutability triggers (`trg_deny_ledger_mutation`) are installed by
  `boot.py` via `install_ledger_triggers()` — no superuser needed.

