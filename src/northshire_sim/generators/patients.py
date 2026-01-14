"""
Patient generator.

Creates a synthetic patient population with demographics, deprivation, geography,
and GP registration fields. Returns a pandas DataFrame (no IO).
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta


def generate_patients(n_patients: int, seed: int) -> pd.DataFrame:
    """
    Generate a synthetic patient dimension-style dataset.
    """
    np.random.seed(seed)

    analysis_date = datetime(2025, 1, 1)

    # 1. Age bands
    age_band_labels = ["16-24", "25-44", "45-64", "65-79", "80+"]
    age_band_probs = [0.12, 0.35, 0.30, 0.18, 0.05]
    age_band = np.random.choice(age_band_labels, size=n_patients, p=age_band_probs)

    def sample_age(band: str) -> int:
        ranges = {
            "16-24": (16, 24),
            "25-44": (25, 44),
            "45-64": (45, 64),
            "65-79": (65, 79),
            "80+": (80, 95),
        }
        lo, hi = ranges[band]
        return np.random.randint(lo, hi + 1)

    age = np.array([sample_age(b) for b in age_band])

    # 2. Sex
    sex_choices = ["F", "M", "Other/Unknown"]
    sex_probs = [0.51, 0.48, 0.01]
    sex = np.random.choice(sex_choices, size=n_patients, p=sex_probs)

    # 3. Ethnicity
    eth_choices = ["White", "Asian", "Black", "Mixed", "Other", None]
    eth_probs = [0.8, 0.065, 0.02, 0.01, 0.005, 0.1]
    ethnicity = np.random.choice(eth_choices, size=n_patients, p=eth_probs)

    # 4. IMD decile (1 = most deprived)
    imd_deciles = np.arange(1, 11)
    imd_probs = [0.18, 0.18, 0.15, 0.10, 0.08, 0.08, 0.07, 0.06, 0.05, 0.05]
    imd_decile = np.random.choice(imd_deciles, size=n_patients, p=imd_probs)

    # Example correlation: more chronic conditions if older & more deprived
    def sample_chronic_conditions(age_val: int, imd: int) -> int:
        base = 0
        if age_val >= 65:
            base += 1
        if imd <= 3:
            base += 1
        lam = 0.5 + 0.3 * base  # Poisson lambda
        return np.random.poisson(lam)

    chronic_conditions_count = np.array(
        [sample_chronic_conditions(a, d) for a, d in zip(age, imd_decile)]
    )

    # 5. Dates
    def random_dob(age_val: int) -> datetime:
        years_delta = age_val
        # Random offset within +/- 6 months
        days_offset = np.random.randint(-183, 184)
        return (analysis_date - timedelta(days=365 * int(years_delta))) + timedelta(
            days=days_offset
        )

    date_of_birth = np.array([random_dob(a).date() for a in age])

    def registration_start(dob):
        min_start = dob.replace(year=dob.year + 16)
        max_start = (analysis_date - timedelta(days=30)).date()
        if min_start > max_start:
            min_start = max_start - timedelta(days=365)
        delta_days = (max_start - min_start).days
        if delta_days <= 0:
            return min_start
        return min_start + timedelta(days=np.random.randint(0, delta_days + 1))

    registration_start_date = np.array([registration_start(dob) for dob in date_of_birth])

    is_active = np.random.choice([True, False], size=n_patients, p=[0.9, 0.1])

    def registration_end(start, active):
        if active:
            return None
        max_end = (analysis_date - timedelta(days=1)).date()
        delta = (max_end - start).days
        if delta <= 0:
            return max_end
        return start + timedelta(days=np.random.randint(1, delta + 1))

    registration_end_date = np.array(
        [registration_end(start, active) for start, active in zip(registration_start_date, is_active)]
    )

    # 6. Synthetic GP practices & geography
    gp_practices = [f"GP_{i:03d}" for i in range(1, 101)]
    registered_gp_practice_id = np.random.choice(gp_practices, size=n_patients)

    lsoa_codes = [f"E010{str(i).zfill(6)}" for i in range(1, 501)]
    postcode_sectors = ["SE15 4", "SE5 0", "E2 8", "N1 2", "SW9 7", "B10 9"]

    lsoa_code = np.random.choice(lsoa_codes, size=n_patients)
    postcode_sector = np.random.choice(postcode_sectors, size=n_patients)

    # 7. Assemble DataFrame
    df_patients = pd.DataFrame(
        {
            "patient_id": np.arange(1, n_patients + 1),
            "nhs_pseudo_id": [f"PSEUDO_{i:06d}" for i in range(1, n_patients + 1)],
            "date_of_birth": date_of_birth,
            "age": age,
            "age_band": age_band,
            "sex": sex,
            "ethnicity_ons": ethnicity,
            "imd_decile": imd_decile,
            "chronic_conditions_count": chronic_conditions_count,
            "lsoa_code": lsoa_code,
            "postcode_sector": postcode_sector,
            "registered_gp_practice_id": registered_gp_practice_id,
            "registration_start_date": registration_start_date,
            "registration_end_date": registration_end_date,
            "is_active": is_active,
        }
    )

    return df_patients
