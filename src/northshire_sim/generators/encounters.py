"""
Encounter generator.

Generates encounter events for patients across a time range
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta

from northshire_sim.generators.gm_reference import ETHNICITY_GROUPS_WITH_DISPARITY

CONDITION_CODES = ["HTN", "DM2", "ASTHMA", "COPD", "ANXIETY", "DEPRESSION", "SCREENING"]

# Encounter type -> provider type mapping (D-29)
ENCOUNTER_TO_PROVIDER_TYPE: dict[str, str] = {
    "GP": "GP_PRACTICE",
    "OP": "ACUTE_HOSPITAL",
    "ED": "URGENT_CARE",
    "IP": "ACUTE_HOSPITAL",
    "COMMUNITY": "COMMUNITY_CLINIC",
    "DIAGNOSTIC": "DIAGNOSTIC_CENTRE",
}


def expected_annual_rate(row) -> float:
    base_rate_by_age = {
        "0-15": 2.0,
        "16-24": 1.5,
        "25-44": 2.0,
        "45-64": 2.5,
        "65-79": 4.0,
        "80+": 6.0,
    }
    rate = base_rate_by_age.get(row["age_band"], 2.0)
    rate += 0.8 * row["chronic_conditions_count"]
    deprivation_factor = (11 - row["imd_decile"]) / 10.0
    rate *= 0.85 + 0.55 * deprivation_factor
    return max(rate, 0.5)


def encounter_type_probs(row) -> dict:
    deprivation_factor = (11 - row["imd_decile"]) / 10.0
    base = {
        "GP": 0.45 - 0.07 * deprivation_factor,
        "OP": 0.20 - 0.05 * deprivation_factor,
        "ED": 0.10 + 0.12 * deprivation_factor,
        "IP": 0.05 + 0.03 * deprivation_factor,
        "COMMUNITY": 0.10 - 0.01 * deprivation_factor,
        "DIAGNOSTIC": 0.10 - 0.02 * deprivation_factor,
    }
    if row["chronic_conditions_count"] >= 2:
        base["OP"] += 0.05
        base["DIAGNOSTIC"] += 0.05
        base["GP"] -= 0.05
    if row["age_band"] in ["0-15", "16-24"]:
        base["IP"] -= 0.02
        base["ED"] += 0.02

    total = sum(base.values())
    for k in base:
        base[k] /= total
    return base


def sample_wait_time_days(enc_type: str, imd_decile: int, ethnicity_ons, rng: np.random.Generator) -> int:
    if enc_type in ["ED", "IP"]:
        return int(rng.integers(0, 2))

    deprivation_factor = (11 - imd_decile) / 10.0
    base_low = int(18 + 60 * deprivation_factor)
    base_high = int(35 + 80 * deprivation_factor)
    base = int(rng.integers(base_low, base_high + 1))

    if ethnicity_ons in {"Pakistani", "Bangladeshi"}:
        base += int(rng.integers(12, 30))
    elif ethnicity_ons in {"Black African", "Black Caribbean"}:
        base += int(rng.integers(8, 25))
    elif ethnicity_ons in ETHNICITY_GROUPS_WITH_DISPARITY:
        base += int(rng.integers(3, 15))

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

    # Build provider type -> provider_id mapping for type-matched assignment (D-29)
    all_provider_ids = providers_df["provider_id"].tolist()
    provider_ids_by_type: dict[str, list[int]] = {}
    for ptype in providers_df["provider_type"].unique():
        provider_ids_by_type[ptype] = providers_df.loc[
            providers_df["provider_type"] == ptype, "provider_id"
        ].tolist()

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

            enc_type = enc_types[i]

            if enc_type == "ED" and enc_start.weekday() < 5 and rng.random() < 0.3:
                weekend_shift = 5 - enc_start.weekday() + int(rng.integers(0, 2))
                candidate = enc_start + timedelta(days=weekend_shift)
                if candidate <= end:
                    enc_start = candidate

            duration_hours = int(rng.integers(1, 8))
            enc_end = enc_start + timedelta(hours=duration_hours)
            wait_days = sample_wait_time_days(enc_type, p["imd_decile"], p["ethnicity_ons"], rng)

            sim_total = (end_date - start_date).days
            if sim_total > 0:
                days_from_start = max(0, (enc_start - start_date).days)
                wait_days = int(wait_days * (1.0 + 0.40 * days_from_start / sim_total))

            target_ptype = ENCOUNTER_TO_PROVIDER_TYPE.get(enc_type, "GP_PRACTICE")
            type_providers = provider_ids_by_type.get(target_ptype, all_provider_ids)
            site_id = rng.choice(type_providers)
            clinician_id = rng.choice(clinician_ids) if len(clinician_ids) > 0 else None

            if enc_type in ["ED", "IP"]:
                priority = "EMERGENCY"
            elif enc_type in ["COMMUNITY", "GP"]:
                priority = rng.choice(["ROUTINE", "URGENT"], p=[0.8, 0.2])
            else:
                priority = rng.choice(["ROUTINE", "URGENT"], p=[0.7, 0.3])

            deprivation_factor = (11 - p["imd_decile"]) / 10.0
            dna_rate = 0.04 + 0.14 * deprivation_factor
            if p["ethnicity_ons"] in {"Pakistani", "Bangladeshi"}:
                dna_rate += 0.08
            elif p["ethnicity_ons"] in {"Black African", "Black Caribbean"}:
                dna_rate += 0.06
            elif p["ethnicity_ons"] in ETHNICITY_GROUPS_WITH_DISPARITY:
                dna_rate += 0.03
            if p["age_band"] in ("16-24", "25-44"):
                dna_rate += 0.05
            elif p["age_band"] in ("65-79", "80+"):
                dna_rate -= 0.02
            dna_rate = max(0.01, min(dna_rate, 0.35))
            was_attended = bool(rng.random() > dna_rate)
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
