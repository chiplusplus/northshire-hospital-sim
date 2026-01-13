DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ehr_readonly') THEN
    CREATE ROLE ehr_readonly LOGIN PASSWORD 'ehr_readonly_pw';
  END IF;
END $$;

GRANT CONNECT ON DATABASE ehr_mirror TO ehr_readonly;
GRANT USAGE ON SCHEMA public TO ehr_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO ehr_readonly;

ALTER DEFAULT PRIVILEGES IN SCHEMA public
GRANT SELECT ON TABLES TO ehr_readonly;
