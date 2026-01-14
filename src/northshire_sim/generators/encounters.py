"""
Encounter generator.

Generates encounter events for patients across a time range
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

CONDITION_CODES = ["HTN", "DM2", "ASTHMA", "COPD", "ANXIETY", "DEPRESSION", "SCREENING"]


def expected_annual_rate(row) -> float:
    base_rate_by_age = {
        "0-17": 1.2,
        "18-39": 1.5,
        "40-64": 2.5,
        "65-79": 4.0,
        "80+": 6.0,
    }
    rate = base_rate_by_age.get(row["age_band"], 2.0)
    rate += 0.8 * row["chronic_conditions_count"]
    if row["imd_decile"] <= 3:
        rate *= 1.2
    elif row["imd_decile"] >= 8:
        rate *= 0.9
    return max(rate, 0.5)


def encounter_type_probs(row) -> dict:
    base = {
        "GP": 0.45,
        "OP": 0.20,
        "ED": 0.10,
        "IP": 0.05,
        "COMMUNITY": 0.10,
        "DIAGNOSTIC": 0.10,
    }
    if row["chronic_conditions_count"] >= 2:
        base["OP"] += 0.05
        base["DIAGNOSTIC"] += 0.05
        base["GP"] -= 0.05
    if row["age_band"] in ["0-17", "18-39"]:
        base["IP"] -= 0.02
        base["ED"] += 0.02

    total = sum(base.values())
    for k in base:
        base[k] /= total
    return base


def sample_wait_time_days(enc_type: str, imd_decile: int, ethnicity_ons, rng: np.random.Generator) -> int:
    if enc_type in ["ED", "IP"]:
        base = int(rng.integers(0, 2))  # 0–1 days
    else:
        base = int(rng.integers(7, 61))
        if imd_decile <= 3:
            base += int(rng.integers(5, 21))
        if ethnicity_ons in ["Black", "Asian", "Mixed"]:
            base += int(rng.integers(0, 11))
    return max(base, 0)


def generate_encounters(
    patients_df: pd.DataFrame,
    providers_df: pd.DataFrame,
    clinicians_df: pd.DataFrame,
    start_date,
    end_date,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    encounters = []

    provider_ids = providers_df["provider_id"].tolist()
    clinician_ids = clinicians_df["clinician_id"].tolist()

    for _, p in patients_df.iterrows():
        start = max(pd.to_datetime(p["registration_start_date"]).date(), start_date)
        end_reg = p["registration_end_date"]
        if pd.isna(end_reg):
            end = end_date
        else:
            end = min(pd.to_datetime(end_reg).date(), end_date)

        if end <= start:
            continue

        days_range = (end - start).days
        if days_range <= 0:
            continue

        years_observed = days_range / 365.0
        lam = expected_annual_rate(p) * years_observed
        n_enc = rng.poisson(lam)
        n_enc = min(n_enc, 40)

        if n_enc == 0:
            continue

        probs = encounter_type_probs(p)
        enc_types = rng.choice(list(probs.keys()), size=n_enc, p=list(probs.values()))

        for i in range(n_enc):
            days_offset = int(rng.integers(0, days_range))
            enc_start = start + timedelta(days=days_offset)

            duration_hours = int(rng.integers(1, 8))
            enc_end = enc_start + timedelta(hours=duration_hours)

            enc_type = enc_types[i]
            wait_days = sample_wait_time_days(enc_type, p["imd_decile"], p["ethnicity_ons"], rng)

            site_id = rng.choice(provider_ids)
            clinician_id = rng.choice(clinician_ids) if len(clinician_ids) > 0 else None

            if enc_type in ["ED", "IP"]:
                priority = "EMERGENCY"
            elif enc_type in ["COMMUNITY", "GP"]:
                priority = rng.choice(["ROUTINE", "URGENT"], p=[0.8, 0.2])
            else:
                priority = rng.choice(["ROUTINE", "URGENT"], p=[0.7, 0.3])

            was_attended = bool(rng.choice([1, 0], p=[0.9, 0.1]))
            first_flag = bool(rng.choice([1, 0], p=[0.3, 0.7]))
            condition = rng.choice(CONDITION_CODES)

            source_system_map = {
                "GP": "APPOINTMENT",
                "OP": "APPOINTMENT",
                "ED": "URGENT_CARE",
                "IP": "EHR",
                "COMMUNITY": "COMMUNITY",
                "DIAGNOSTIC": "DIAGNOSTIC",
            }

            encounters.append(
                {
                    "patient_id": p["patient_id"],
                    "encounter_id": None,
                    "encounter_datetime_start": enc_start,
                    "encounter_datetime_end": enc_end,
                    "encounter_type": enc_type,
                    "source_system": source_system_map[enc_type],
                    "provider_id": site_id,
                    "clinician_id": clinician_id,
                    "priority": priority,
                    "was_attended": was_attended,
                    "first_attendance_flag": first_flag,
                    "primary_condition_code": condition,
                    "wait_time_days": wait_days,
                    "created_at": datetime.utcnow(),
                }
            )

    enc_df = pd.DataFrame(encounters)
    if not enc_df.empty:
        enc_df["encounter_id"] = np.arange(1, len(enc_df) + 1)
        enc_df = enc_df[
            [
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
        ]

    return enc_df
