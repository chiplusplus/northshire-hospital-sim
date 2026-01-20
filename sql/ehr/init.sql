BEGIN;

-- -----------------------
-- PATIENT DEMOGRAPHICS
-- -----------------------
CREATE TABLE IF NOT EXISTS patient_demographics (
    patient_id                 BIGINT PRIMARY KEY,
    nhs_pseudo_id              VARCHAR(32) NOT NULL UNIQUE,

    date_of_birth              DATE NOT NULL,
    age                        INT,
    age_band                   VARCHAR(16),

    sex                        VARCHAR(16),
    ethnicity_ons              VARCHAR(64),

    imd_decile                 INT CHECK (imd_decile BETWEEN 1 AND 10),
    chronic_conditions_count   INT CHECK (chronic_conditions_count >= 0),

    lsoa_code                  VARCHAR(16),
    postcode_sector            VARCHAR(16),

    registered_gp_practice_id  VARCHAR(32),
    registration_start_date    DATE,
    registration_end_date      DATE,
    is_active                  BOOLEAN NOT NULL DEFAULT TRUE,

    updated_at                 TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_patient_lsoa      ON patient_demographics(lsoa_code);
CREATE INDEX IF NOT EXISTS idx_patient_postcode  ON patient_demographics(postcode_sector);
CREATE INDEX IF NOT EXISTS idx_patient_imd       ON patient_demographics(imd_decile);


-- -----------------------
-- ENCOUNTERS
-- -----------------------
CREATE TABLE IF NOT EXISTS encounters (
    encounter_id               BIGINT PRIMARY KEY,
    patient_id                 BIGINT NOT NULL REFERENCES patient_demographics(patient_id),

    -- In this simulator, provider_id is the "site/provider" dimension key
    provider_id                BIGINT NOT NULL,

    encounter_datetime_start   TIMESTAMP NOT NULL,
    encounter_datetime_end     TIMESTAMP NOT NULL,

    encounter_type             VARCHAR(32),
    source_system              VARCHAR(32),

    clinician_id               BIGINT,
    priority                   VARCHAR(16),

    was_attended               BOOLEAN,
    first_attendance_flag      BOOLEAN,

    primary_condition_code     VARCHAR(32),
    wait_time_days             INT CHECK (wait_time_days IS NULL OR wait_time_days >= 0),

    created_at                 TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMP NOT NULL DEFAULT NOW(),

    CHECK (encounter_datetime_end >= encounter_datetime_start)
);

CREATE INDEX IF NOT EXISTS idx_enc_patient   ON encounters(patient_id);
CREATE INDEX IF NOT EXISTS idx_enc_provider  ON encounters(provider_id);
CREATE INDEX IF NOT EXISTS idx_enc_start_dt  ON encounters(encounter_datetime_start);
CREATE INDEX IF NOT EXISTS idx_enc_type      ON encounters(encounter_type);


-- -----------------------
-- DIAGNOSES (coded post-event; can lag)
-- -----------------------
CREATE TABLE IF NOT EXISTS diagnoses (
    diagnosis_id               BIGSERIAL PRIMARY KEY,
    patient_id                 BIGINT NOT NULL REFERENCES patient_demographics(patient_id),
    encounter_id               BIGINT REFERENCES encounters(encounter_id),

    diagnosis_code             VARCHAR(32) NOT NULL,
    diagnosis_desc             VARCHAR(255),

    diagnosis_type             VARCHAR(32),     -- PRIMARY / SECONDARY
    coded_datetime             TIMESTAMP,       -- when coding team entered it
    clinical_datetime          TIMESTAMP,       -- when it clinically occurred (often encounter date)

    source_system              VARCHAR(32) DEFAULT 'EHR',
    created_at                 TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_diag_patient    ON diagnoses(patient_id);
CREATE INDEX IF NOT EXISTS idx_diag_encounter  ON diagnoses(encounter_id);
CREATE INDEX IF NOT EXISTS idx_diag_code       ON diagnoses(diagnosis_code);


-- -----------------------
-- PROCEDURES (also coded post-event)
-- -----------------------
CREATE TABLE IF NOT EXISTS procedures (
    procedure_id               BIGSERIAL PRIMARY KEY,
    patient_id                 BIGINT NOT NULL REFERENCES patient_demographics(patient_id),
    encounter_id               BIGINT REFERENCES encounters(encounter_id),

    procedure_code             VARCHAR(32) NOT NULL,
    procedure_desc             VARCHAR(255),

    coded_datetime             TIMESTAMP,
    clinical_datetime          TIMESTAMP,

    source_system              VARCHAR(32) DEFAULT 'EHR',
    created_at                 TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_proc_patient    ON procedures(patient_id);
CREATE INDEX IF NOT EXISTS idx_proc_encounter  ON procedures(encounter_id);
CREATE INDEX IF NOT EXISTS idx_proc_code       ON procedures(procedure_code);

COMMIT;
