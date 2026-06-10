-- Urgent Care internal reporting DB schema (Northshire Trust)
-- Represents a separate operational system providing a read-only analytics view.

BEGIN;

CREATE TABLE IF NOT EXISTS urgent_care_logs (
    uc_log_id              BIGINT PRIMARY KEY,

    -- Patient & site context
    patient_id               BIGINT NOT NULL,
    provider_id              BIGINT NOT NULL,

    -- Optional linkage back to EHR encounters (often missing / imperfect)
    encounter_id             BIGINT,

    -- ED flow timestamps
    arrival_datetime           TIMESTAMP NOT NULL,
    triage_datetime            TIMESTAMP,
    seen_by_clinician_datetime TIMESTAMP,
    departure_datetime         TIMESTAMP,

    -- Operational attributes
    triage_category          VARCHAR(16),     -- e.g. 1–5 or "RED/AMBER/GREEN"
    presenting_complaint     VARCHAR(128),
    outcome      VARCHAR(32),     -- ADMITTED / DISCHARGED / TRANSFERRED / LEFT

    -- Data lineage
    source_system            VARCHAR(32) NOT NULL DEFAULT 'URGENT_CARE',
    created_at               TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at               TIMESTAMP NOT NULL DEFAULT NOW(),

    -- Light sanity constraints
    CHECK (triage_datetime IS NULL OR triage_datetime >= arrival_datetime),
    CHECK (seen_by_clinician_datetime IS NULL OR seen_by_clinician_datetime >= arrival_datetime),
    CHECK (departure_datetime IS NULL OR departure_datetime >= arrival_datetime)
);

-- Indexes mainly to support extraction & refresh, not analytics
CREATE INDEX IF NOT EXISTS idx_uc_patient        ON urgent_care_logs(patient_id);
CREATE INDEX IF NOT EXISTS idx_uc_provider       ON urgent_care_logs(provider_id);
CREATE INDEX IF NOT EXISTS idx_uc_arrival_dt     ON urgent_care_logs(arrival_datetime);
CREATE INDEX IF NOT EXISTS idx_uc_encounter_id   ON urgent_care_logs(encounter_id);

COMMIT;
