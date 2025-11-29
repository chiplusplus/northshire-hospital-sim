CREATE TABLE patient_demographics (
    patient_id              BIGINT PRIMARY KEY,
    nhs_pseudo_id           VARCHAR(32) NOT NULL,
    date_of_birth           DATE NOT NULL,
    age                     INT,
    age_band                VARCHAR(16),
    sex                     VARCHAR(16),
    ethnicity_ons           VARCHAR(64),
    imd_decile              INT,
    chronic_conditions_count INT,
    lsoa_code               VARCHAR(32),
    postcode_sector         VARCHAR(16),
    registered_gp_practice_id VARCHAR(32),
    registration_start_date DATE,
    registration_end_date   DATE,
    is_active               BOOLEAN
);

CREATE TABLE encounters (
    encounter_id            BIGSERIAL PRIMARY KEY,
    patient_id              BIGINT NOT NULL,
    provider_id              BIGINT NOT NULL,
    encounter_datetime_start TIMESTAMP NOT NULL,
    encounter_datetime_end   TIMESTAMP NOT NULL,
    encounter_type          VARCHAR(32),
    source_system           VARCHAR(32),
    site_id                 BIGINT,
    clinician_id            BIGINT,
    priority                VARCHAR(16),
    was_attended            BOOLEAN,
    first_attendance_flag   BOOLEAN,
    primary_condition_code  VARCHAR(32),
    wait_time_days          INT,
    created_at              TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_encounters_patient ON encounters(patient_id);
CREATE INDEX idx_encounters_datetime ON encounters(encounter_datetime_start);
