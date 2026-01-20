-- Urgent Care MIRROR: create and configure a read-only consumer user.
-- Run this against the *urgent_care_mirror* database.

BEGIN;

CREATE SCHEMA IF NOT EXISTS public;

-- Role to hold readonly permissions
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'urgent_readonly') THEN
    CREATE ROLE urgent_readonly;
  END IF;
END$$;

-- Login user (what access-iq uses to connect)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'urgent_ro_user') THEN
    CREATE ROLE urgent_ro_user LOGIN PASSWORD 'urgent_ro_pw';
  END IF;
END$$;

GRANT urgent_readonly TO urgent_ro_user;

-- Hardening: stop object creation in public schema
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE CREATE ON SCHEMA public FROM urgent_ro_user;

-- Allow connect + usage
GRANT CONNECT ON DATABASE urgent_care_mirror TO urgent_ro_user;
GRANT USAGE ON SCHEMA public TO urgent_readonly;

-- Existing objects
GRANT SELECT ON ALL TABLES IN SCHEMA public TO urgent_readonly;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO urgent_readonly;

-- Future objects created by the refresh user
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT ON TABLES TO urgent_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO urgent_readonly;

COMMIT;
