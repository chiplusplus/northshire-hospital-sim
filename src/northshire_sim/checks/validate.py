"""
Dataset validation utilities (fail-fast integrity checks).

This module defines:
- small reusable assertions (columns, PK uniqueness, FK integrity)
- table-level validators (patients/providers/etc.)
- dataset-level validator (validate_dataset)

These checks are structural invariants:
- schema presence
- primary key uniqueness
- foreign key integrity
- basic time sanity

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional

import pandas as pd


# -------------------------
# Core assertion helpers
# -------------------------

def assert_required_columns(df: pd.DataFrame, required: Iterable[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise AssertionError(f"[{name}] Missing required columns: {missing}")


def assert_unique_key(df: pd.DataFrame, key: str, name: str, allow_empty: bool = False) -> None:
    if df.empty:
        if allow_empty:
            return
        raise AssertionError(f"[{name}] DataFrame is empty (unexpected).")

    if key not in df.columns:
        raise AssertionError(f"[{name}] Key column '{key}' not found in DataFrame.")

    if not df[key].is_unique:
        examples = df.loc[df[key].duplicated(), key].head(10).tolist()
        raise AssertionError(f"[{name}] Key '{key}' is not unique. Examples: {examples}")


def assert_fk(child: pd.Series, parent: pd.Series, label: str, allow_nulls: bool = True) -> None:
    if child is None or parent is None:
        return

    child_vals = child.dropna() if allow_nulls else child
    parent_vals = parent.dropna()

    bad = set(child_vals) - set(parent_vals)
    if bad:
        examples = list(bad)[:10]
        raise AssertionError(f"[FK] {label} contains values not found in parent. Examples: {examples}")


def assert_datetime_order(
    df: pd.DataFrame,
    start_col: str,
    end_col: str,
    name: str,
    allow_equal: bool = True,
    allow_null_end: bool = False,
) -> None:
    if df.empty:
        return
    if start_col not in df.columns or end_col not in df.columns:
        return

    start = pd.to_datetime(df[start_col], errors="coerce")
    end = pd.to_datetime(df[end_col], errors="coerce")

    if not allow_null_end and end.isna().any():
        bad_rows = df[end.isna()].head(5)
        raise AssertionError(f"[{name}] Null values found in '{end_col}' (not allowed). Example rows:\n{bad_rows}")

    # Ignore rows where end is null if allowed
    mask = ~end.isna() if allow_null_end else pd.Series([True] * len(df), index=df.index)

    if allow_equal:
        bad = mask & (end < start)
    else:
        bad = mask & (end <= start)

    if bad.any():
        bad_rows = df.loc[bad, [start_col, end_col]].head(10)
        raise AssertionError(
            f"[{name}] '{end_col}' is earlier than '{start_col}' for some rows.\n{bad_rows}"
        )


# -------------------------
# Table-level validators
# -------------------------

def validate_patients(patients: pd.DataFrame) -> None:
    required = [
        "patient_id",
        "nhs_pseudo_id",
        "date_of_birth",
        "age",
        "age_band",
        "sex",
        "ethnicity_ons",
        "imd_decile",
        "chronic_conditions_count",
        "lsoa_code",
        "postcode_sector",
        "registered_gp_practice_id",
        "registration_start_date",
        "registration_end_date",
        "is_active",
    ]
    assert_required_columns(patients, required, "patients")
    assert_unique_key(patients, "patient_id", "patients", allow_empty=False)

    # Registration end can be null for active patients
    assert_datetime_order(
        patients,
        start_col="registration_start_date",
        end_col="registration_end_date",
        name="patients",
        allow_equal=True,
        allow_null_end=True,
    )


def validate_providers(providers: pd.DataFrame) -> None:
    required = [
        "provider_id",
        "provider_code",
        "provider_name",
        "provider_type",
        "postcode_sector",
        "lsoa_code",
        "is_active",
    ]
    assert_required_columns(providers, required, "providers")
    assert_unique_key(providers, "provider_id", "providers", allow_empty=False)


def validate_clinicians(clinicians: pd.DataFrame, providers: pd.DataFrame) -> None:
    # Clinicians can be empty in tiny smoke runs; allow that
    required = [
        "clinician_id",
        "clinician_code",
        "provider_id",
        "role",
        "specialty",
        "grade_band",
        "fte",
        "start_date",
        "end_date",
        "is_active",
    ]
    assert_required_columns(clinicians, required, "clinicians")
    assert_unique_key(clinicians, "clinician_id", "clinicians", allow_empty=True)

    if not clinicians.empty:
        assert_fk(
            clinicians["provider_id"],
            providers["provider_id"],
            "clinicians.provider_id -> providers.provider_id",
        )

        # end_date can be null for active clinicians
        assert_datetime_order(
            clinicians,
            start_col="start_date",
            end_col="end_date",
            name="clinicians",
            allow_equal=True,
            allow_null_end=True,
        )


def validate_encounters(
    encounters: pd.DataFrame,
    patients: pd.DataFrame,
    providers: pd.DataFrame,
    clinicians: pd.DataFrame,
) -> None:
    required = [
        "encounter_id",
        "patient_id",
        "encounter_datetime_start",
        "encounter_datetime_end",
        "encounter_type",
        "source_system",
        "provider_id",
        "clinician_id",
        "priority",
        "was_attended",
        "first_attendance_flag",
        "primary_condition_code",
        "wait_time_days",
        "created_at",
    ]
    assert_required_columns(encounters, required, "encounters")
    assert_unique_key(encounters, "encounter_id", "encounters", allow_empty=False)

    assert_fk(
        encounters["patient_id"],
        patients["patient_id"],
        "encounters.patient_id -> patients.patient_id",
    )
    assert_fk(
        encounters["provider_id"],
        providers["provider_id"],
        "encounters.provider_id -> providers.provider_id",
    )

    # clinician_id can be null; validate only non-null values if we have clinicians
    if not clinicians.empty and "clinician_id" in encounters.columns:
        assert_fk(
            encounters["clinician_id"],
            clinicians["clinician_id"],
            "encounters.clinician_id -> clinicians.clinician_id",
            allow_nulls=True,
        )

    assert_datetime_order(
        encounters,
        start_col="encounter_datetime_start",
        end_col="encounter_datetime_end",
        name="encounters",
        allow_equal=True,
        allow_null_end=False,
    )


def validate_referrals(referrals: pd.DataFrame, patients: pd.DataFrame, providers: pd.DataFrame) -> None:
    # Referrals can be empty depending on sampling; allow empty
    required = [
        "referral_id",
        "patient_id",
        "source_provider_id",
        "target_provider_id",
        # one of these should exist depending on your generator:
        # "referral_datetime" OR "referral_date"
    ]
    assert_required_columns(referrals, ["referral_id", "patient_id", "source_provider_id", "target_provider_id"], "referrals")
    assert_unique_key(referrals, "referral_id", "referrals", allow_empty=True)

    if referrals.empty:
        return

    assert_fk(referrals["patient_id"], patients["patient_id"], "referrals.patient_id -> patients.patient_id")
    assert_fk(referrals["source_provider_id"], providers["provider_id"], "referrals.source_provider_id -> providers.provider_id")
    assert_fk(referrals["target_provider_id"], providers["provider_id"], "referrals.target_provider_id -> providers.provider_id")


def validate_diagnoses(
    diagnoses: pd.DataFrame,
    patients: pd.DataFrame,
    encounters: pd.DataFrame,
) -> None:
    required = [
        "diagnosis_id",
        "patient_id",
        "encounter_id",
        "diagnosis_code",
        "diagnosis_desc",
        "diagnosis_type",
        "coded_datetime",
        "clinical_datetime",
        "source_system",
    ]
    assert_required_columns(diagnoses, required, "diagnoses")
    assert_unique_key(diagnoses, "diagnosis_id", "diagnoses", allow_empty=True)

    if diagnoses.empty:
        return

    assert_fk(diagnoses["patient_id"], patients["patient_id"], "diagnoses.patient_id -> patients.patient_id")
    assert_fk(diagnoses["encounter_id"], encounters["encounter_id"], "diagnoses.encounter_id -> encounters.encounter_id")
    assert_datetime_order(diagnoses, "clinical_datetime", "coded_datetime", "diagnoses", allow_equal=True, allow_null_end=False)


def validate_diagnostics(
    diagnostics: pd.DataFrame,
    patients: pd.DataFrame,
    providers: pd.DataFrame,
    encounters: pd.DataFrame,
    referrals: Optional[pd.DataFrame] = None,
) -> None:
    # Diagnostics can be empty; allow empty
    required = [
        "diagnostic_id",
        "patient_id",
        "provider_id",
        "test_type",
        "test_panel",
        "request_date",
        "performed_date",
        "result_date",
        "result_flag",
        "encounter_id",
        "referral_id",
    ]
    assert_required_columns(diagnostics, required, "diagnostics")
    assert_unique_key(diagnostics, "diagnostic_id", "diagnostics", allow_empty=True)

    if diagnostics.empty:
        return

    assert_fk(diagnostics["patient_id"], patients["patient_id"], "diagnostics.patient_id -> patients.patient_id")
    assert_fk(diagnostics["provider_id"], providers["provider_id"], "diagnostics.provider_id -> providers.provider_id")

    # encounter_id/referral_id are allowed to be null (data quality issues), validate only non-null
    assert_fk(
        diagnostics["encounter_id"],
        encounters["encounter_id"],
        "diagnostics.encounter_id -> encounters.encounter_id",
        allow_nulls=True,
    )

    if referrals is not None and not referrals.empty and "referral_id" in diagnostics.columns:
        assert_fk(
            diagnostics["referral_id"],
            referrals["referral_id"],
            "diagnostics.referral_id -> referrals.referral_id",
            allow_nulls=True,
        )

    # Basic ordering sanity for dates (nulls not expected here)
    assert_datetime_order(diagnostics, "request_date", "performed_date", "diagnostics", allow_equal=True, allow_null_end=False)
    assert_datetime_order(diagnostics, "performed_date", "result_date", "diagnostics", allow_equal=True, allow_null_end=False)


def validate_urgent_care(
    urgent_care: pd.DataFrame,
    encounters: pd.DataFrame,
    patients: pd.DataFrame,
    providers: pd.DataFrame,
    clinicians: pd.DataFrame,
) -> None:
    # Urgent care can be empty if there are no ED encounters; allow empty
    required = [
        "uc_log_id",
        "encounter_id",
        "patient_id",
        "provider_id",
        "arrival_datetime",
        "triage_datetime",
        "seen_by_clinician_datetime",
        "departure_datetime",
    ]
    assert_required_columns(urgent_care, required, "urgent_care")
    assert_unique_key(urgent_care, "uc_log_id", "urgent_care", allow_empty=True)

    if urgent_care.empty:
        return

    assert_fk(urgent_care["encounter_id"], encounters["encounter_id"], "urgent_care.encounter_id -> encounters.encounter_id")
    assert_fk(urgent_care["patient_id"], patients["patient_id"], "urgent_care.patient_id -> patients.patient_id")
    assert_fk(urgent_care["provider_id"], providers["provider_id"], "urgent_care.provider_id -> providers.provider_id")

    if not clinicians.empty and "clinician_id" in urgent_care.columns:
        assert_fk(
            urgent_care["clinician_id"],
            clinicians["clinician_id"],
            "urgent_care.clinician_id -> clinicians.clinician_id",
            allow_nulls=True,
        )

    assert_datetime_order(urgent_care, "arrival_datetime", "departure_datetime", "urgent_care", allow_equal=True, allow_null_end=False)
    assert_datetime_order(urgent_care, "arrival_datetime", "triage_datetime", "urgent_care", allow_equal=True, allow_null_end=False)
    assert_datetime_order(urgent_care, "arrival_datetime", "seen_by_clinician_datetime", "urgent_care", allow_equal=True, allow_null_end=False)


# -------------------------
# Dataset-level validator
# -------------------------

def validate_dataset(dfs: Dict[str, pd.DataFrame]) -> None:
    """
    Validate the full generated dataset (core tables).
    Expects the following keys in dfs:
    - patients, providers, clinicians, encounters, referrals, diagnoses, diagnostics, urgent_care
    """
    required_keys = ["patients", "providers", "clinicians", "encounters", "referrals", "diagnoses", "diagnostics", "urgent_care"]
    missing = [k for k in required_keys if k not in dfs]
    if missing:
        raise AssertionError(f"[validate_dataset] Missing DataFrames in dict: {missing}")

    patients = dfs["patients"]
    providers = dfs["providers"]
    clinicians = dfs["clinicians"]
    encounters = dfs["encounters"]
    referrals = dfs["referrals"]
    diagnoses = dfs["diagnoses"]
    diagnostics = dfs["diagnostics"]
    urgent_care = dfs["urgent_care"]

    validate_patients(patients)
    validate_providers(providers)
    validate_clinicians(clinicians, providers)
    validate_encounters(encounters, patients, providers, clinicians)
    validate_referrals(referrals, patients, providers)
    validate_diagnoses(diagnoses, patients, encounters)
    validate_diagnostics(diagnostics, patients, providers, encounters, referrals=referrals)
    validate_urgent_care(urgent_care, encounters, patients, providers, clinicians)
