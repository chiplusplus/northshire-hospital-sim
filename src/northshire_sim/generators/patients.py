"""
Patient generator.

SYNTHETIC DATA — NOT REAL PATIENTS.

Creates a synthetic patient population with demographics, deprivation, geography,
and GP registration fields modelled on Greater Manchester. Returns a pandas
DataFrame (no IO).

NHS numbers use the Mod-11 check-digit algorithm per NHS Data Dictionary.
~95% are valid; ~5% are intentionally invalid for quarantine testing.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from northshire_sim.generators.gm_reference import (
    AGE_BAND_LABELS,
    AGE_BAND_PROBS,
    AGE_BAND_RANGES,
    ETHNICITY_IMD_BIAS,
    GM_ETHNICITY_CATEGORIES,
    GM_ETHNICITY_PROBS,
    GM_GP_PRACTICES,
    GM_LSOA_IMD_LOOKUP,
)


# ---------------------------------------------------------------------------
# NHS Mod-11 number generation (D-01, D-03, D-04)
# ---------------------------------------------------------------------------

_MOD11_WEIGHTS = [10, 9, 8, 7, 6, 5, 4, 3, 2]


def _generate_nhs_number(rng: np.random.Generator) -> str:
    """Generate a valid NHS Mod-11 check-digit number (10 digits)."""
    while True:
        digits = [int(d) for d in rng.integers(0, 10, size=9)]
        remainder = sum(d * w for d, w in zip(digits, _MOD11_WEIGHTS)) % 11
        check = 11 - remainder
        if check == 11:
            check = 0
        if check == 10:
            continue  # invalid combination — regenerate
        digits.append(check)
        return "".join(str(d) for d in digits)


def _invalidate_nhs_number(nhs_number: str, rng: np.random.Generator) -> str:
    """Flip one digit to break checksum while keeping 10-digit format."""
    digits = list(nhs_number)
    pos = int(rng.integers(0, 9))  # flip a non-check digit
    original = int(digits[pos])
    replacement = (original + int(rng.integers(1, 10))) % 10
    digits[pos] = str(replacement)
    return "".join(digits)


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------


def generate_patients(n_patients: int, seed: int, analysis_date: datetime | None = None) -> pd.DataFrame:
    """
    Generate a synthetic patient dimension-style dataset.

    Uses np.random.default_rng(seed) for reproducible, modern seeding (D-18).
    """
    rng = np.random.default_rng(seed)

    if analysis_date is None:
        analysis_date = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    # ----- 1. Age bands (D-21) — includes 0-15 paediatric -----
    age_band = rng.choice(AGE_BAND_LABELS, size=n_patients, p=AGE_BAND_PROBS)

    def _sample_age(band: str) -> int:
        lo, hi = AGE_BAND_RANGES[band]
        return int(rng.integers(lo, hi + 1))

    age = np.array([_sample_age(b) for b in age_band])

    # ----- 2. Sex (D-22) — unchanged -----
    sex_choices = ["F", "M", "Other/Unknown"]
    sex_probs = [0.51, 0.48, 0.01]
    sex = rng.choice(sex_choices, size=n_patients, p=sex_probs)

    # ----- 3. Ethnicity — ONS 2021 Census GM (D-20) -----
    ethnicity = rng.choice(GM_ETHNICITY_CATEGORIES, size=n_patients, p=GM_ETHNICITY_PROBS)

    # ----- 4. Geography — LSOA-derived IMD & postcode (D-05, D-07) -----
    # Weight by inverse decile, with ethnicity-IMD correlation:
    # South Asian and Black populations skew toward deprived LSOAs.
    base_weights = np.array(
        [1.0 / e["imd_decile"] for e in GM_LSOA_IMD_LOOKUP], dtype=float
    )
    base_weights /= base_weights.sum()
    imd_deciles_lookup = np.array([e["imd_decile"] for e in GM_LSOA_IMD_LOOKUP])

    lsoa_indices = np.empty(n_patients, dtype=int)
    ethnicity_list = [str(e) if e is not None else "" for e in ethnicity]

    for eth_str in set(ethnicity_list):
        mask = np.array(ethnicity_list) == eth_str
        n_group = mask.sum()
        if n_group == 0:
            continue
        bias = ETHNICITY_IMD_BIAS.get(eth_str, 0.0) if eth_str else 0.0
        if bias > 0:
            w = base_weights * np.where(imd_deciles_lookup <= 3, 1.0 + 4.0 * bias, 1.0)
            w /= w.sum()
        else:
            w = base_weights
        lsoa_indices[mask] = rng.choice(len(GM_LSOA_IMD_LOOKUP), size=n_group, p=w)

    lsoa_entries = [GM_LSOA_IMD_LOOKUP[i] for i in lsoa_indices]
    lsoa_code = [e["lsoa_code"] for e in lsoa_entries]
    imd_decile = np.array([e["imd_decile"] for e in lsoa_entries])
    postcode_sector = [e["postcode_sector"] for e in lsoa_entries]

    # ----- 5. Chronic conditions (D-23) — smooth IMD gradient + age -----
    def _sample_chronic_conditions(age_val: int, imd: int) -> int:
        deprivation_factor = (11 - imd) / 10.0
        age_factor = 0.0
        if age_val >= 45:
            age_factor += 0.3
        if age_val >= 65:
            age_factor += 0.5
        if age_val >= 80:
            age_factor += 0.4
        lam = 0.2 + 1.8 * deprivation_factor + age_factor
        return int(rng.poisson(lam))

    chronic_conditions_count = np.array(
        [_sample_chronic_conditions(a, d) for a, d in zip(age, imd_decile)]
    )

    # ----- 6. Dates -----
    def _random_dob(age_val: int) -> datetime:
        days_offset = int(rng.integers(-183, 184))
        return (analysis_date - timedelta(days=365 * int(age_val))) + timedelta(
            days=days_offset
        )

    date_of_birth = np.array([_random_dob(a).date() for a in age])

    def _registration_start(dob, age_val: int):
        """Registration start date. Children (0-15) registered at birth."""
        if age_val <= 15:
            # Paediatric: registered at birth
            min_start = dob
        else:
            min_start = dob.replace(year=dob.year + 16)
        max_start = (analysis_date - timedelta(days=30)).date()
        if min_start > max_start:
            min_start = max_start - timedelta(days=365)
        delta_days = (max_start - min_start).days
        if delta_days <= 0:
            return min_start
        return min_start + timedelta(days=int(rng.integers(0, delta_days + 1)))

    registration_start_date = np.array(
        [_registration_start(dob, a) for dob, a in zip(date_of_birth, age)]
    )

    is_active = rng.choice([True, False], size=n_patients, p=[0.9, 0.1])

    def _registration_end(start, active):
        if active:
            return None
        max_end = (analysis_date - timedelta(days=1)).date()
        delta = (max_end - start).days
        if delta <= 0:
            return max_end
        return start + timedelta(days=int(rng.integers(1, delta + 1)))

    registration_end_date = np.array(
        [_registration_end(s, a) for s, a in zip(registration_start_date, is_active)]
    )

    # ----- 7. GP practices — P-prefixed ODS-style codes (D-08) -----
    practice_ids = [p["practice_id"] for p in GM_GP_PRACTICES]
    registered_gp_practice_id = rng.choice(practice_ids, size=n_patients)

    # ----- 8. NHS numbers — Mod-11 with ~5% intentional invalids (D-01, D-03) -----
    n_valid = int(n_patients * 0.95)
    nhs_numbers: list[str] = []
    seen: set[str] = set()
    for i in range(n_patients):
        nhs_num = _generate_nhs_number(rng)
        while nhs_num in seen:
            nhs_num = _generate_nhs_number(rng)
        if i >= n_valid:
            nhs_num = _invalidate_nhs_number(nhs_num, rng)
        seen.add(nhs_num)
        nhs_numbers.append(nhs_num)

    # ----- 9. Assemble DataFrame -----
    df_patients = pd.DataFrame(
        {
            "patient_id": np.arange(1, n_patients + 1),
            "nhs_pseudo_id": nhs_numbers,
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
