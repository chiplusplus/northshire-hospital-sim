"""
Referral generator.

Generates referral events for patients, including target providers and specialties.
"""

import numpy as np
import pandas as pd



def generate_referrals(
    encounters_df: pd.DataFrame,
    providers_df: pd.DataFrame,
    seed: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    specialties = [
        "Cardiology",
        "Respiratory",
        "Diabetes",
        "Mental Health",
        "MSK",
        "Dermatology",
        "ENT",
        "Ophthalmology",
        "Gastroenterology",
    ]

    referral_types = ["ROUTINE", "URGENT"]
    referral_probs = [0.8, 0.2]

    providers = providers_df.copy()
    targetable = providers[providers["provider_type"].isin(["ACUTE_HOSPITAL", "COMMUNITY_CLINIC", "DIAGNOSTIC_CENTRE"])]

    # Choose a subset of encounters to generate referrals from (unchanged logic)
    sampled = encounters_df.sample(frac=0.35, replace=False, random_state=seed)
    n = len(sampled)

    if n == 0:
        return pd.DataFrame(columns=[
            "referral_id",
            "patient_id",
            "source_provider_id",
            "target_provider_id",
            "referral_datetime",
            "referral_type",
            "referral_specialty",
            "status",
        ])

    enc_dates = pd.to_datetime(sampled["encounter_datetime_start"])
    wait_days_col = sampled["wait_time_days"].values.astype(int)
    jitter = rng.integers(0, 8, size=n)
    offset_days = -(wait_days_col + jitter)
    referral_dates = enc_dates + pd.to_timedelta(offset_days, unit="D")
    target_provider_ids = rng.choice(targetable["provider_id"].tolist(), size=n)

    referral_type = rng.choice(referral_types, size=n, p=referral_probs)
    referral_specialty = rng.choice(specialties, size=n)

    status = rng.choice(["OPEN", "CLOSED"], size=n, p=[0.3, 0.7])

    df = pd.DataFrame(
        {
            "referral_id": np.arange(1, n + 1),
            "patient_id": sampled["patient_id"].values,
            "source_provider_id": sampled["provider_id"].values,
            "target_provider_id": target_provider_ids,
            "referral_datetime": referral_dates,
            "treatment_datetime": enc_dates.values,
            "wait_time_days": wait_days_col,
            "referral_type": referral_type,
            "referral_specialty": referral_specialty,
            "status": status,
        }
    )

    return df
