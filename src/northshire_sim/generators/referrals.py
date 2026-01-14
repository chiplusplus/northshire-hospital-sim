"""
Referral generator.

Generates referral events for patients, including target providers and specialties.
"""

import numpy as np
import pandas as pd


def random_dates(rng, n: int, start, end):
    """
    Return n random dates between start and end (inclusive-ish).
    start, end: strings or Timestamps ('2020-01-01')
    """
    start = pd.to_datetime(start)
    end = pd.to_datetime(end)
    days = (end - start).days
    offsets = rng.integers(0, days + 1, size=n)
    return start + pd.to_timedelta(offsets, unit="D")


def generate_referrals(
    encounters_df: pd.DataFrame,
    providers_df: pd.DataFrame,
    seed: int,
    start="2023-01-01",
    end="2024-12-31",
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
    sampled = encounters_df.sample(frac=0.35, replace=False, random_state=42)
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

    referral_dates = random_dates(rng, n, start, end)
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
            "referral_type": referral_type,
            "referral_specialty": referral_specialty,
            "status": status,
        }
    )

    return df
