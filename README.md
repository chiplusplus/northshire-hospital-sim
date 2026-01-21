# northshire-hospital-sim

A lightweight “client-side” simulator for the **Northshire NHS Trust** case study.  
This repo exists to expose realistic upstream data sources that the analytics platform (**access-iq**) ingests into S3 Bronze.

This is **not** the main portfolio repo — it’s the simulated client environment so the engineering work in **access-iq** can build on a solid, real-world-esque base.

---

## What this repo simulates

Northshire Trust exposes multiple data feeds externally:

1) **EHR read-only PostgreSQL mirror**  
2) **Urgent care read-only PostgreSQL mirror**  
3) **Secure SFTP outbound drops (appointments)**  
4) **Trust-owned S3 exports (diagnostics + provider reference)**  

---

## Quick start

### Prerequisites
- Docker + Docker Compose
- Python 3.x
- AWS CLI
- Named AWS profile (e.g. `northshire-trust`) with write access to configured S3 buckets

### Run everything
```bash
make trust
```

### Reset everything
```bash
make reset
```

---

## Sources exposed for access-iq

### EHR Postgres mirror (read-only)
- DB: `ehr_mirror`
- Tables: `patient_demographics`, `encounters`
- Access via DSN in `config/sources.yaml`

### Urgent care Postgres mirror (read-only)
- DB: `urgent_care_mirror`
- Table: `urgent_care_logs`

### SFTP outbound drops
- Folder: `/upload/outbound/appointments`
- Files: `YYYY-MM-DD_appointments.csv`

### S3 exports
- Diagnostics: `exports/diagnostics/export_date=YYYY-MM-DD/*.csv`
- Provider reference: `exports/providers/sites_and_services_master.xlsx`

Local cache:
```
data/s3_exports/<bucket>/<key>
```

---

## Repo Structure
northshire-hospital-sim/
├─ README.md
├─ Makefile
├─ docker-compose.yml
├─ requirements.txt             
│
├─ config/
│  └─ sources.yaml               # connection details + S3 bucket names
│
├─ sql/
│  ├─ ehr/
│  │  ├─ init.sql
│  │  └─ init_mirror_readonly.sql
│  └─ urgent_care/
│  │  ├─ init.sql
│     └─ init_mirror_readonly.sql
│
├─ src/northshire_sim/
│  │
│  ├─ generators/                # pure dataframe generators
│  │  ├─ patients.py
│  │  ├─ encounters.py
│  │  ├─ clinicians.py
│  │  ├─ providers.py
│  │  ├─ referrals.py
│  │  ├─ diagnostics.py
│  │  └─ urgent_care.py
│  │
│  ├─ exports/                   # build “files/feeds” from generated dataframes
│  │  └─ exports.py              
│  │
│  ├─ checks/                    # sanity/consistency checks across dfs
│  │  └─ validate.py
│  │
│  └─ publishing/                # write to DB/S3/SFTP “drops”
│     ├─ db.py                   # helpers: connect, truncate, bulk load
│     ├─ ehr.py                  # load_ehr logic
│     ├─ urgent_care.py          # load_logs logic
│     ├─ s3.py                   # upload files to buckets
│     └─ mirror.py               # refresh_ehr_mirror logic
│
├─ scripts/                      # thin CLI entrypoints only
│  ├─ generate_data.py           # orchestrates generators + checks + writes “staging” outputs
│  ├─ publish_ehr.py             # loads internal EHR and refreshes mirror
│  ├─ publish_urgent_care.py     # loads urgent care DB and mirror (if you add mirror)
│  ├─ publish_s3.py              # diagnostics + provider excel upload
│  ├─ publish_sftp.py            # writes appointment drops to local “sftp_drop/”
│  └─ trust.py                   # one command: generate + publish everything
│
└─ data/                         # generated artefacts (gitignored)
   ├─ staging/                   # intermediate outputs (parquet/csv)
   ├─ sftp_drop/                 # local folder that simulates SFTP
   ├─ s3_exports/                # local cache of what's uploaded
   └─ logs/

---

## Notes
- All generated artefacts live under `data/` (gitignored)
- Mirrors enforce read-only access
- This repo is intentionally lightweight and story-focused
