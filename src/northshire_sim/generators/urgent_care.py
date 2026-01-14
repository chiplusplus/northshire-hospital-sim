"""
Urgent care logs generator.

Builds a synthetic urgent care (ED) operational log dataset derived from ED
encounters. This simulates a separate urgent-care system that logs ED activit
"""

import pandas as pd
import numpy as np
from datetime import timedelta


# ----------------------------
# Configuration / Categories
# ----------------------------

TRIAGE_CATEGORIES = ["Cat 1", "Cat 2", "Cat 3", "Cat 4", "Cat 5"]
MODE_CHOICES = ["AMBULANCE", "WALK_IN", "GP_REFERRAL", "OTHER"]
PRESENTING_COMPLAINTS = [
    "Chest pain",
    "Shortness of breath",
    "Abdominal pain",
    "Headache",
    "Injury",
    "Fever",
    "Mental health crisis",
    "General unwell",
]
OUTCOMES = ["ADMITTED", "DISCHARGED", "REFERRED", "LEFT_BEFORE_SEEN"]


# ----------------------------
# Helper functions (logic unchanged)
# ----------------------------

def _triage_probs(priority: str):
    """Return triage probability vector based on encounter priority (unchanged)."""
    if priority == "EMERGENCY":
        return [0.2, 0.4, 0.25, 0.1, 0.05]
    return [0.05, 0.15, 0.35, 0.30, 0.15]


def _is_high_risk(priority: str, imd_decile) -> bool:
    """Determine high-risk flag for mode-of-arrival weighting (unchanged)."""
    return (priority == "EMERGENCY") or (imd_decile is not None and pd.to_numeric(imd_decile) <= 3)


def _mode_probs(high_risk: bool):
    """Return mode-of-arrival probability vector (unchanged)."""
    if high_risk:
        return [0.55, 0.25, 0.15, 0.05]  # more ambulances
    return [0.20, 0.60, 0.15, 0.05]


def _outcome_probs(triage_category: str):
    """Return outcome probability vector based on triage category (unchanged)."""
    if triage_category in ["Cat 1", "Cat 2"]:
        return [0.55, 0.25, 0.15, 0.05]
    return [0.20, 0.65, 0.10, 0.05]


def _discharge_destination(outcome: str, rng: np.random.Generator) -> str:
    """Map outcome -> discharge destination (unchanged)."""
    if outcome == "ADMITTED":
        return "WARD"
    if outcome == "REFERRED":
        return "ANOTHER_PROVIDER"
    if outcome == "LEFT_BEFORE_SEEN":
        return rng.choice(["HOME", "OTHER"])
    return rng.choice(["HOME", "OUTPATIENT_FOLLOWUP"])


# ----------------------------
# Public API
# ----------------------------

def generate_urgent_care_logs(
    encounters_df: pd.DataFrame,
    patients_df: pd.DataFrame,
    providers_df: pd.DataFrame,
    seed: int = 42,
) -> pd.DataFrame:
    """
    Build a realistic urgent care logs dataset from ED encounters.

    This simulates a separate urgent-care system that logs ED activity and is exposed
    to you as a read-only SQL view.
    """
    rng = np.random.default_rng(seed)

    # 1) Take only ED encounters
    ed = encounters_df[encounters_df["encounter_type"] == "ED"].copy()
    if ed.empty:
        return pd.DataFrame()

    # 2) Join patient demographics & geography
    patient_cols = [
        "patient_id",
        "nhs_pseudo_id",
        "ethnicity_ons",
        "imd_decile",
        "postcode_sector",
        "lsoa_code",
    ]
    ed = ed.merge(
        patients_df[patient_cols],
        on="patient_id",
        how="left",
        suffixes=("", "_pat"),
    )

    # 3) (Optional) Join provider info (if you want to use provider_type later)
    ed = ed.merge(
        providers_df[["provider_id", "provider_type"]],
        on="provider_id",
        how="left",
        suffixes=("", "_prov"),
    )

    # 4) Build logs row-by-row from encounters (unchanged)
    records = []

    for row in ed.itertuples(index=False):
        arrival = pd.to_datetime(str(row.encounter_datetime_start))
        departure = pd.to_datetime(str(row.encounter_datetime_end))

        # Ensure departure is after arrival
        if departure <= arrival:
            departure = arrival + timedelta(hours=float(rng.integers(1, 6)))

        total_minutes = int((departure - arrival).total_seconds() // 60)

        # Triage within 0–30 mins
        wait_to_triage = int(rng.integers(0, 31))
        triage_dt = arrival + timedelta(minutes=wait_to_triage)

        # Seen by clinician within 10–180 mins from arrival, but <= total stay
        wait_to_seen = int(rng.integers(10, min(181, max(11, total_minutes + 1))))
        seen_dt = arrival + timedelta(minutes=wait_to_seen)

        # Triage category: sicker patients / emergency priority more likely Cat 1–2
        triage_cat = rng.choice(TRIAGE_CATEGORIES, p=_triage_probs(str(row.priority)))

        # Mode of arrival: more ambulance for emergency / older / deprived
        high_risk = _is_high_risk(str(row.priority), row.imd_decile)
        mode = rng.choice(MODE_CHOICES, p=_mode_probs(high_risk))

        # Outcome: rough rule-of-thumb based on priority/triage
        outcome = rng.choice(OUTCOMES, p=_outcome_probs(triage_cat))

        # Discharge destination linked to outcome
        dest = _discharge_destination(outcome, rng)

        # Presenting complaint loosely related to condition code (if you want)
        complaint = rng.choice(PRESENTING_COMPLAINTS)

        records.append(
            {
                "uc_log_id": None,  # filled after DataFrame
                "encounter_id": row.encounter_id,
                "patient_id": row.patient_id,
                "nhs_pseudo_id": getattr(row, "nhs_pseudo_id", None),
                "arrival_datetime": arrival,
                "triage_datetime": triage_dt,
                "seen_by_clinician_datetime": seen_dt,
                "departure_datetime": departure,
                "triage_category": triage_cat,
                "presenting_complaint": complaint,
                "mode_of_arrival": mode,
                "outcome": outcome,
                "discharge_destination": dest,
                "wait_minutes_to_triage": wait_to_triage,
                "wait_minutes_to_seen": wait_to_seen,
                "total_time_in_dept_minutes": total_minutes,
                "provider_id": row.provider_id,
                "clinician_id": row.clinician_id,
                "postcode_sector": getattr(row, "postcode_sector", None),
                "lsoa_code": getattr(row, "lsoa_code", None),
                "ethnicity_ons": getattr(row, "ethnicity_ons", None),
                "imd_decile": pd.to_numeric(row.imd_decile) if getattr(row, "imd_decile", None) is not None else None,
            }
        )

    df = pd.DataFrame(records)

    # 5) Finalise IDs + column order (unchanged)
    if not df.empty:
        df["uc_log_id"] = np.arange(1, len(df) + 1)
        df = df[
            [
                "uc_log_id",
                "encounter_id",
                "patient_id",
                "nhs_pseudo_id",
                "arrival_datetime",
                "triage_datetime",
                "seen_by_clinician_datetime",
                "departure_datetime",
                "triage_category",
                "presenting_complaint",
                "mode_of_arrival",
                "outcome",
                "discharge_destination",
                "wait_minutes_to_triage",
                "wait_minutes_to_seen",
                "total_time_in_dept_minutes",
                "provider_id",
                "clinician_id",
                "postcode_sector",
                "lsoa_code",
                "ethnicity_ons",
                "imd_decile",
            ]
        ]

    return df


def degrade_urgent_care_quality(df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """
    Introduce realistic data quality issues into urgent care logs (unchanged).
    """
    rng = np.random.default_rng(seed)
    df = df.copy()

    n = len(df)
    if n == 0:
        return df

    # 5% missing nhs_pseudo_id
    mask = rng.random(n) < 0.05
    df.loc[mask, "nhs_pseudo_id"] = None

    # 7% missing ethnicity
    mask = rng.random(n) < 0.07
    df.loc[mask, "ethnicity_ons"] = None

    # 5% missing postcode_sector
    mask = rng.random(n) < 0.05
    df.loc[mask, "postcode_sector"] = None

    # Mix triage coding styles a bit
    mask = rng.random(n) < 0.10
    df.loc[mask, "triage_category"] = df.loc[mask, "triage_category"].str.replace("Cat ", "CAT", regex=False)

    mask = rng.random(n) < 0.15
    df.loc[mask, "triage_category"] = df.loc[mask, "triage_category"].str[-1]  # just '1', '2', ...

    return df
