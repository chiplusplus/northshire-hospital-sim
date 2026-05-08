# Northshire Hospital Sim - End-to-End Test Runbook

## 0) Preconditions

* Docker + Docker Compose installed
* Python installed (and your venv activated if you use one)
* AWS CLI installed
* AWS profile configured (named IAM profile)

  * `aws configure list-profiles` includes `northshire-trust`
  * `AWS_PROFILE=northshire-trust aws sts get-caller-identity` returns expected account
* `config/sources.yaml` exists and has:

  * Postgres DSNs (ehr internal/mirror, urgent internal/mirror)
  * S3 config (profile/role + bucket names)
  * SFTP config (host/port/user/pass)

---

## 1) Clean start

From repo root:

```bash
make down-v
rm -rf data/staging data/sftp_drop data/s3_exports
```

Expected:

* No containers running
* Local generated artefacts removed

---

## 2) Boot infra only

```bash
make up
docker ps
```

Expected:

* Containers running for:

  * `ehr_internal`, `ehr_mirror`, `urgent_internal`, `urgent_mirror`, `northshire_sftp`
  * `northshire_sftp` shows `(healthy)` after ~30s

If SFTP is not healthy:

```bash
docker compose logs -f sftp
```

---

## 3) Generate staging data

```bash
make generate
```

Expected:

* `data/staging/core/` contains:

  * `patients.csv`
  * `encounters.csv`
  * `urgent_care_logs.csv`
  * (plus the others you generate)
* `data/staging/exports/` contains:

  * `appointments/*_appointments.csv`
  * `diagnostics/*_diagnostic_orders.csv`
  * `providers/sites_and_services_master.xlsx`

Quick check:

```bash
ls -lah data/staging/core | head
ls -lah data/staging/exports/appointments | head
ls -lah data/staging/exports/diagnostics | head
ls -lah data/staging/exports/providers
```

---

## 4) Publish EHR internal + mirror

```bash
make publish-ehr
```

Expected output:

* Internal load completes
* Mirror refresh completes
* Read-only grants applied

Sanity queries (internal):

```bash
psql -h localhost -p 5433 -U ehr_admin -d ehr -c "select count(*) from patient_demographics;"
psql -h localhost -p 5433 -U ehr_admin -d ehr -c "select count(*) from encounters;"
```

Sanity queries (mirror as read-only user):

```bash
psql -h localhost -p 5434 -U ehr_ro_user -d ehr_mirror -c "select count(*) from patient_demographics;"
psql -h localhost -p 5434 -U ehr_ro_user -d ehr_mirror -c "select count(*) from encounters;"
```

Expected:

* Mirror counts match internal counts
* Read-only user can SELECT

Negative test (mirror should reject writes):

```bash
psql -h localhost -p 5434 -U ehr_ro_user -d ehr_mirror -c "create table should_fail(id int);"
```

Expected:

* Permission denied (good)

---

## 5) Publish urgent care internal + mirror

```bash
make publish-urgent
```

Sanity queries (internal):

```bash
psql -h localhost -p 5435 -U urgent_admin -d urgent_care -c "select count(*) from urgent_care_logs;"
```

Sanity queries (mirror as read-only user):

```bash
psql -h localhost -p 5436 -U urgent_ro_user -d urgent_care_mirror -c "select count(*) from urgent_care_logs;"
```

Expected:

* Mirror count matches internal count
* Read-only user can SELECT

Negative test:

```bash
psql -h localhost -p 5436 -U urgent_ro_user -d urgent_care_mirror -c "delete from urgent_care_logs;"
```

Expected:

* Permission denied (good)

---

## 6) Publish SFTP drops (appointments)

```bash
make publish-sftp
```

Expected:

* Files copied into local SFTP drop:

  * `data/sftp_drop/outbound/appointments/*.csv`

Verify locally:

```bash
ls -lah data/sftp_drop/outbound/appointments | head
```

Verify via SFTP (actual endpoint your platform will use):

```bash
sftp -P 2222 trust_sftp@localhost
# password: trust_sftp_pw
ls upload/outbound/appointments
exit
```

Expected:

* Appointment CSVs visible via SFTP

---

## 7) Publish S3 exports (diagnostics + providers)

Before running, verify you are using the correct AWS identity:

```bash
AWS_PROFILE=northshire-trust aws sts get-caller-identity
```

Then:

```bash
make publish-s3
```

Expected:

* Diagnostics files uploaded under a partitioned prefix, e.g.

  * `exports/diagnostics/export_date=YYYY-MM-DD/...`
* Provider excel uploaded under:

  * `exports/providers/sites_and_services_master.xlsx`
* Local cache populated under:

  * `data/s3_exports/<bucket>/<key>...`

Local cache check:

```bash
find data/s3_exports -maxdepth 4 -type f | head -n 20
```

Optional: list objects in S3 (diagnostics bucket name from sources.yaml):

```bash
AWS_PROFILE=northshire-trust aws s3 ls s3://<DIAGNOSTICS_BUCKET>/exports/diagnostics/ --recursive | head
AWS_PROFILE=northshire-trust aws s3 ls s3://<PROVIDERS_BUCKET>/exports/providers/ --recursive
```

Expected:

* Objects exist in S3
* Local cache mirrors the key structure

---

## 8) Full end-to-end “one command”

Now test the full orchestrator:

```bash
make down-v
rm -rf data/staging data/sftp_drop data/s3_exports
make trust
```

Expected:

* Everything runs in order
* Final message indicates completion
* Repeat quick checks:

  * mirror DBs accessible as read-only
  * SFTP lists appointment files
  * S3 uploads + local cache present

---

# Pass/Fail Criteria

You “pass” if all are true:

* `make trust` succeeds from a clean start
* EHR mirror and urgent care mirror:

  * contain data
  * read-only users can SELECT
  * read-only users cannot write
* SFTP endpoint:

  * is healthy
  * shows exported appointment files via `sftp`
* S3:

  * has diagnostics + providers objects
  * local cache `data/s3_exports/...` mirrors uploads

If any fail, the simulator is not ready for `access-iq`.

