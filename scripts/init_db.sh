#!/usr/bin/env bash
set -e

# Initialize DB roles and grant rules for PHALANX
# Application role has INSERT/SELECT only on ledger_events to guarantee audit immutability

APP_PASSWORD="${PHALANX_APP_DB_PASSWORD:?PHALANX_APP_DB_PASSWORD is required}"

if [ -z "$APP_PASSWORD" ]; then
  echo "ERROR: PHALANX_APP_DB_PASSWORD (or POSTGRES_PASSWORD) environment variable is required to initialize phalanx_app role" >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v app_pwd="$APP_PASSWORD" <<-EOSQL
  DO \$\$
  BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'phalanx_app') THEN
      CREATE ROLE phalanx_app WITH LOGIN;
    END IF;
  END
  \$\$;

  ALTER ROLE phalanx_app WITH PASSWORD :'app_pwd';

  GRANT CONNECT ON DATABASE "$POSTGRES_DB" TO phalanx_app;
  GRANT ALL ON SCHEMA public TO phalanx_app;

  -- Default grants for future tables created by migrations
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO phalanx_app;
  ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO phalanx_app;
EOSQL

echo "PHALANX application role 'phalanx_app' successfully configured."
