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
# Helper functions
# ----------------------------

def _triage_probs(priority: str):
    """Return triage probability vector based on encounter priority."""
    if priority == "EMERGENCY":
        return [0.2, 0.4, 0.25, 0.1, 0.05]
    return [0.05, 0.15, 0.35, 0.30, 0.15]


def _is_high_risk(priority: str, imd_decile) -> bool:
    """Determine high-risk flag for mode-of-arrival weighting."""
    return (priority == "EMERGENCY") or (imd_decile is not None and pd.to_numeric(imd_decile) <= 3)


def _mode_probs(high_risk: bool):
    """Return mode-of-arrival probability vector."""
    if high_risk:
        return [0.55, 0.25, 0.15, 0.05]
    return [0.20, 0.60, 0.15, 0.05]


def _outcome_probs(triage_category: str, imd_decile: int = 5):
    """Return outcome probability vector. Deprived patients more likely to leave before seen."""
    deprivation_factor = max(0.0, (11 - imd_decile) / 10.0)
    left_boost = 0.08 * deprivation_factor
    if triage_category in ["Cat 1", "Cat 2"]:
        return [0.55, 0.25, 0.15 - left_boost / 2, 0.05 + left_boost / 2]
    return [0.20, 0.65 - left_boost, 0.10, 0.05 + left_boost]


def _discharge_destination(outcome: str, rng: np.random.Generator) -> str:
    """Map outcome -> discharge destination."""
    if outcome == "ADMITTED":
        return "WARD"
    if outcome == "REFERRED":
        return "ANOTHER_PROVIDER"
    if outcome == "LEFT_BEFORE_SEEN":
        return rng.choice(["HOME", "OTHER"])
    return rng.choice(["HOME", "OUTPATIENT_FOLLOWUP"])


def _sample_arrival_hour(imd_decile: int, month: int, day_of_week: int, rng: np.random.Generator) -> int:
    """Sample realistic ED arrival hour.

    Affluent: clear morning peak (10-14), moderate evening.
    Deprived: flatter daytime, heavy evening/night (poor GP access).
    Weekend: suppressed daytime (no GP redirect), boosted evening/night.
    Winter: amplified evening and overnight spike.
    """
    deprivation_factor = max(0.0, (11 - imd_decile) / 10.0)
    is_winter = month in (11, 12, 1, 2)
    is_weekend = day_of_week >= 5

    weights = np.array([
        2.0, 1.5, 1.0, 1.0, 1.0, 1.5,
        3.0, 5.0, 7.0, 9.0,
        12.0, 14.0, 13.0, 11.0,
        9.0, 8.0, 7.0, 8.0,
        10.0, 11.0, 9.0, 7.0,
        5.0, 3.0,
    ])

    for h in range(18, 24):
        weights[h] *= 1.0 + 0.8 * deprivation_factor
    for h in range(0, 6):
        weights[h] *= 1.0 + 1.5 * deprivation_factor
    for h in range(9, 16):
        weights[h] *= 1.0 - 0.35 * deprivation_factor

    if is_weekend:
        for h in range(24):
            weights[h] *= 1.3
        for h in range(9, 14):
            weights[h] *= 0.7
        for h in range(18, 24):
            weights[h] *= 1.5
        for h in range(0, 6):
            weights[h] *= 1.4

    if is_winter:
        for h in range(17, 24):
            weights[h] *= 1.4
        for h in range(0, 6):
            weights[h] *= 1.3

    weights /= weights.sum()
    return int(rng.choice(24, p=weights))


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

    # 4) Pre-compute provider-level speed multipliers (staffing variation)
    uc_providers = sorted(
        providers_df[providers_df["provider_type"] == "URGENT_CARE"]["provider_id"].unique()
    )
    provider_speed = {}
    speed_values = [1.25, 1.10, 0.90, 1.15]
    for i, pid in enumerate(uc_providers):
        provider_speed[pid] = speed_values[i % len(speed_values)]

    # 5) Build logs row-by-row with deprivation-driven timing
    records = []

    for row in ed.itertuples(index=False):
        imd = pd.to_numeric(row.imd_decile) if getattr(row, "imd_decile", None) is not None else 5
        deprivation_factor = max(0.0, (11 - imd) / 10.0)

        arrival = pd.to_datetime(str(row.encounter_datetime_start))

        # Realistic arrival hour based on deprivation + season + day-of-week
        hour = _sample_arrival_hour(imd, arrival.month, arrival.weekday(), rng)
        minute = int(rng.integers(0, 60))
        arrival = arrival.replace(hour=hour, minute=minute)

        is_winter = arrival.month in (11, 12, 1, 2)
        prov_mult = provider_speed.get(row.provider_id, 1.0)

        # Total time in department: normal distribution shifted by deprivation + winter
        mean_stay = 155 + 60 * deprivation_factor
        std_stay = 55 + 10 * deprivation_factor
        if is_winter:
            mean_stay += 30 + 20 * deprivation_factor
        mean_stay *= prov_mult
        total_minutes = max(30, int(rng.normal(mean_stay, std_stay)))

        # 12-hour breach tail: rare extreme stays for deprived patients
        if deprivation_factor > 0.6 and is_winter and rng.random() < 0.02:
            total_minutes = max(total_minutes, int(rng.integers(720, 960)))
        elif deprivation_factor > 0.6 and rng.random() < 0.005:
            total_minutes = max(total_minutes, int(rng.integers(720, 840)))

        departure = arrival + timedelta(minutes=total_minutes)

        # Triage wait: deprived patients wait longer (busier ED)
        max_triage_wait = int((15 + 30 * deprivation_factor) * prov_mult)
        wait_to_triage = int(rng.integers(0, max_triage_wait + 1))
        triage_dt = arrival + timedelta(minutes=wait_to_triage)

        # Wait to be seen: strongly IMD-dependent + provider variation
        min_wait_seen = int((10 + 40 * deprivation_factor) * prov_mult)
        max_wait_seen = min(int((60 + 120 * deprivation_factor) * prov_mult), max(min_wait_seen + 1, total_minutes - 10))
        wait_to_seen = int(rng.integers(min_wait_seen, max_wait_seen + 1))
        seen_dt = arrival + timedelta(minutes=wait_to_seen)

        # Triage category
        triage_cat = rng.choice(TRIAGE_CATEGORIES, p=_triage_probs(str(row.priority)))

        # Mode of arrival
        high_risk = _is_high_risk(str(row.priority), row.imd_decile)
        mode = rng.choice(MODE_CHOICES, p=_mode_probs(high_risk))

        # Outcome: deprived patients more likely to leave before being seen
        outcome = rng.choice(OUTCOMES, p=_outcome_probs(triage_cat, imd))

        # Discharge destination
        dest = _discharge_destination(outcome, rng)

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
