-- Initialize DB roles and grant rules
-- Application role has INSERT/SELECT only on ledger_events to guarantee audit immutability

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'phalanx_app') THEN
    CREATE ROLE phalanx_app WITH LOGIN PASSWORD 'Maitray@7979';
  ELSE
    ALTER ROLE phalanx_app WITH PASSWORD 'Maitray@7979';
  END IF;
END
$$;
GRANT CONNECT ON DATABASE phalanx_db TO phalanx_app;
GRANT USAGE ON SCHEMA public TO phalanx_app;

-- Default grants for future tables created by migrations
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO phalanx_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO phalanx_app;

-- Note: Migration scripts that create ledger_events explicitly revoke UPDATE, DELETE, TRUNCATE from phalanx_app.
