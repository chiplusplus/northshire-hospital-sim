# northshire-hospital-sim

## Repo Structure
northshire-hospital-sim/
├─ README.md
├─ Makefile
├─ docker-compose.yml
├─ .env.example
├─ requirements.txt             
│
├─ config/
│  ├─ settings.yaml              # counts, date ranges, seeds, paths
│  └─ sources.yaml               # connection details + S3 bucket names
│
├─ sql/
│  ├─ ehr/
│  │  ├─ init.sql
│  │  └─ init_mirror_readonly.sql
│  └─ urgent_care/
│     └─ init.sql
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
│  ├─ publishing/                # write to DB/S3/SFTP “drops”
│  │  ├─ db.py                   # helpers: connect, truncate, bulk load
│  │  ├─ ehr.py                  # load_ehr logic
│  │  ├─ urgent_care.py          # load_logs logic
│  │  ├─ s3.py                   # upload files to buckets
│  │  └─ mirror.py               # refresh_ehr_mirror logic
│  │
│  └─ runtime/
│     └─ paths.py                # where to put generated outputs locally
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
│  ├─ staging/                   # intermediate outputs (parquet/csv)
│  ├─ sftp_drop/                 # local folder that simulates SFTP
│  ├─ s3_exports/                # local cache of what's uploaded
│  └─ logs/


