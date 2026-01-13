CREATE TABLE urgent_care_logs (
    uc_log_id                  BIGSERIAL PRIMARY KEY,
    encounter_id               BIGINT NOT NULL,
    patient_id                 BIGINT,
    nhs_pseudo_id              VARCHAR(64),
    arrival_datetime           TIMESTAMP NOT NULL,
    triage_datetime            TIMESTAMP,
    seen_by_clinician_datetime TIMESTAMP,
    departure_datetime         TIMESTAMP,
    triage_category            VARCHAR(20),     -- e.g. 'Cat 1', 'Cat 2'
    presenting_complaint       TEXT,
    mode_of_arrival            VARCHAR(30),     -- 'AMBULANCE', 'WALK_IN', etc.
    outcome                    VARCHAR(40),     -- 'ADMITTED', 'DISCHARGED', etc.
    discharge_destination      VARCHAR(60),     -- 'HOME', 'WARD', 'ANOTHER_PROVIDER'
    wait_minutes_to_triage     INT,
    wait_minutes_to_seen       INT,
    total_time_in_dept_minutes INT,
    provider_id                INT,
    clinician_id               INT,
    postcode_sector            VARCHAR(16),
    lsoa_code                  VARCHAR(16),
    ethnicity_ons              VARCHAR(32),
    imd_decile                 INT,
    created_at                 TIMESTAMP DEFAULT now()
);
