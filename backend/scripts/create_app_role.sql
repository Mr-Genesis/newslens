-- G2 S0b: provision a NON-SUPERUSER application role so Postgres Row-Level Security is a LIVE
-- control in production (not theatre). The default `newslens` role is a superuser and bypasses RLS,
-- so per-user isolation today relies solely on the app's explicit current_user_id() filter. Run
-- this as a superuser, then point the app's DATABASE_URL at newslens_app.
--
-- Usage:
--   psql "$ADMIN_DATABASE_URL" -v app_password="$NEWSLENS_APP_PASSWORD" -f create_app_role.sql
--   then set DATABASE_URL=postgresql+asyncpg://newslens_app:<pw>@<host>/newslens
--
-- The app role MUST be able to do everything the app needs (DML on every table, sequences, schema
-- usage) but MUST be NOSUPERUSER + NOBYPASSRLS so the *_user_isolation policies apply to it.

CREATE ROLE newslens_app LOGIN PASSWORD :'app_password' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

GRANT USAGE ON SCHEMA public TO newslens_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO newslens_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO newslens_app;

-- Future tables/sequences (migrations create them as the owner) inherit these grants:
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO newslens_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO newslens_app;

-- Verify: this should print 'off'
-- SET ROLE newslens_app; SELECT current_setting('is_superuser'); RESET ROLE;
