-- scripts/neon_check.sql
-- Read-only diagnostic queries for verifying Neon PostgreSQL state in PHALANX.
-- STRICT: No DDL, no DML. Read-only queries only.

-- 1. Current user and database connection details
SELECT 
    current_user AS session_user,
    current_database() AS current_database,
    version() AS postgres_version;

-- 2. Alembic migration version
SELECT version_num FROM alembic_version;

-- 3. List all relational tables in the public schema
SELECT 
    table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
  AND table_type = 'BASE TABLE'
ORDER BY table_name;

-- 4. Verify whether ledger-immutability trigger exists
-- Trigger name: trg_deny_ledger_mutation on table ledger_events
SELECT 
    trigger_name,
    event_manipulation,
    event_object_table,
    action_statement,
    action_timing
FROM information_schema.triggers
WHERE event_object_table = 'ledger_events'
  AND trigger_name = 'trg_deny_ledger_mutation';

-- Also verify trigger function binding
SELECT 
    t.tgname AS trigger_name,
    c.relname AS table_name,
    p.proname AS function_name
FROM pg_trigger t
JOIN pg_class c ON t.tgrelid = c.oid
JOIN pg_proc p ON t.tgfoid = p.oid
WHERE c.relname = 'ledger_events'
  AND t.tgname = 'trg_deny_ledger_mutation';

-- 5. Count of rows in key tables
SELECT 'alembic_version' AS table_name, COUNT(*) AS row_count FROM alembic_version
UNION ALL
SELECT 'agent_budgets', COUNT(*) FROM agent_budgets
UNION ALL
SELECT 'budget_reservations', COUNT(*) FROM budget_reservations
UNION ALL
SELECT 'idempotency_records', COUNT(*) FROM idempotency_records
UNION ALL
SELECT 'step_up_approvals', COUNT(*) FROM step_up_approvals
UNION ALL
SELECT 'mandates', COUNT(*) FROM mandates
UNION ALL
SELECT 'ledger_events', COUNT(*) FROM ledger_events
UNION ALL
SELECT 'daily_quotas', COUNT(*) FROM daily_quotas
ORDER BY table_name;
