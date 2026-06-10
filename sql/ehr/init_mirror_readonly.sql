-- EHR MIRROR: create and configure a read-only consumer user.

BEGIN;

-- 1) Ensure schema exists (public usually exists, but this is harmless)
CREATE SCHEMA IF NOT EXISTS public;

-- 2) Create a dedicated role for read-only access
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ehr_readonly') THEN
    CREATE ROLE ehr_readonly;
  END IF;
END$$;

-- 3) Create a login user for external consumers 

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ehr_ro_user') THEN
    CREATE ROLE ehr_ro_user LOGIN PASSWORD 'ehr_ro_pw';
  END IF;
END$$;

-- 4) Make the user inherit permissions from the read-only role
GRANT ehr_readonly TO ehr_ro_user;

-- 5) Basic hardening: prevent object creation in public schema
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM ehr_ro_user;

-- 6) Allow connect + usage
GRANT CONNECT ON DATABASE ehr_mirror TO ehr_ro_user;
GRANT USAGE ON SCHEMA public TO ehr_readonly;

-- 7) Grant read access to existing tables/sequences
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ehr_readonly;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO ehr_readonly;

-- 8) Ensure future tables/sequences in public automatically grant SELECT
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO ehr_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO ehr_readonly;

COMMIT;
