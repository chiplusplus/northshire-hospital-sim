# northshire-hospital-sim

## Repo Structure
northshire-hospital-sim/
  docker-compose.yml          # for postgres (and optional extra DB)
  requirements.txt
  generators/
    generate_patients.py
    generate_providers.py
    generate_clinicians.py
    generate_encounters.py
    generate_diagnostics.py
    generate_community_care.py
    generate_gp_registrations.py
    generate_urgent_care_logs.py
    generate_appointments.py
    master_generate_all.py
  dynamic_exports/
    init.sql                  # schema + basic index creation
    load_ehr.py               # loads CSVs into postgres
  exports/
    sftp/
      appointments/
        2025-01-01_appointments.csv
        2025-01-02_appointments.csv
      gp_registrations/
        2025-01_gp_registrations.csv
      esr/
        2025-01_esr_clinical_staff.csv
    s3_trust/
      diagnostics_orders/
        dt=2025-01-01/orders.csv
        dt=2025-01-02/orders.csv
      community_care/
        dt=2025-01-01/community.csv
        dt=2025-01-02/community.csv
    excel/
      northshire_providers.xlsx
  scripts/
    build_ehr_db.sh
    generate_feeds.sh
  README.md
