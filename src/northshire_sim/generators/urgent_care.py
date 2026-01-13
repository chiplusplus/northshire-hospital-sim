import pandas as pd
import numpy as np
from datetime import timedelta

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

    # 1. Take only ED encounters
    ed = encounters_df[encounters_df["encounter_type"] == "ED"].copy()
    
    if ed.empty:
        return pd.DataFrame()

    # 2. Join patient demographics & geography
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

    # 3. (Optional) Join provider info (if you want to use provider_type later)
    ed = ed.merge(
        providers_df[["provider_id", "provider_type"]],
        on="provider_id",
        how="left",
        suffixes=("", "_prov"),
    )

    # 4. Define helper distributions
    triage_categories = ["Cat 1", "Cat 2", "Cat 3", "Cat 4", "Cat 5"]
    mode_choices = ["AMBULANCE", "WALK_IN", "GP_REFERRAL", "OTHER"]
    presenting_complaints = [
        "Chest pain",
        "Shortness of breath",
        "Abdominal pain",
        "Headache",
        "Injury",
        "Fever",
        "Mental health crisis",
        "General unwell",
    ]
    outcomes = ["ADMITTED", "DISCHARGED", "REFERRED", "LEFT_BEFORE_SEEN"]

    records = []

    for row in ed.itertuples(index=False):
        # Convert encounter datetime columns to ensure they are datetime objects
        arrival = pd.to_datetime(str(row.encounter_datetime_start))
        departure = pd.to_datetime(str(row.encounter_datetime_end))

        # Skip rows with missing/invalid datetimes
        if pd.isna(arrival) or pd.isna(departure):
            continue

        # Sanity check: if departure is before arrival, fix it
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
        if row.priority == "EMERGENCY":
            triage_probs = [0.2, 0.4, 0.25, 0.1, 0.05]
        else:
            triage_probs = [0.05, 0.15, 0.35, 0.30, 0.15]

        triage_cat = rng.choice(triage_categories, p=triage_probs)

        # Mode of arrival: more ambulance for emergency / older / deprived
        high_risk = (
            (row.priority == "EMERGENCY")
            or (row.imd_decile is not None and pd.to_numeric(row.imd_decile) <= 3)
        )
        
        if high_risk:
            mode_probs = [0.55, 0.25, 0.15, 0.05]  # more ambulances
        else:
            mode_probs = [0.20, 0.60, 0.15, 0.05]

        mode = rng.choice(mode_choices, p=mode_probs)

        # Outcome: rough rule-of-thumb based on priority/triage
        if triage_cat in ["Cat 1", "Cat 2"]:
            outcome_probs = [0.55, 0.25, 0.15, 0.05]
        else:
            outcome_probs = [0.20, 0.65, 0.10, 0.05]

        outcome = rng.choice(outcomes, p=outcome_probs)

        # Discharge destination linked to outcome
        if outcome == "ADMITTED":
            dest = "WARD"
        elif outcome == "REFERRED":
            dest = "ANOTHER_PROVIDER"
        elif outcome == "LEFT_BEFORE_SEEN":
            dest = rng.choice(["HOME", "OTHER"])
        else:
            dest = rng.choice(["HOME", "OUTPATIENT_FOLLOWUP"])

        # Presenting complaint loosely related to condition code (if you want)
        complaint = rng.choice(presenting_complaints)

        record = {
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
        records.append(record)

    df = pd.DataFrame(records)
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