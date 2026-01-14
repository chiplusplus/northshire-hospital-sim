"""
Clinician/workforce generator.

Creates a synthetic clinician dimension dataset, allocated to providers.
"""

import numpy as np
import pandas as pd
from datetime import date


def generate_clinicians(providers_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    records = []

    roles_by_type = {
        "ACUTE_HOSPITAL": ["Consultant", "Registrar", "Staff Nurse", "Physiotherapist", "Radiologist"],
        "GP_PRACTICE": ["GP Partner", "Salaried GP", "Practice Nurse", "Healthcare Assistant"],
        "COMMUNITY_CLINIC": ["Community Nurse", "Physiotherapist", "Occupational Therapist", "Psychologist"],
        "URGENT_CARE": ["ED Doctor", "ED Nurse", "Paramedic"],
        "DIAGNOSTIC_CENTRE": ["Radiologist", "Sonographer", "Radiographer"],
    }

    specialties = [
        "General Medicine", "Cardiology", "Respiratory", "Diabetes",
        "Emergency Medicine", "Radiology", "Primary Care",
        "Mental Health", "Physiotherapy", "Geriatrics",
    ]

    bands = ["Band 5", "Band 6", "Band 7", "Band 8a", "Consultant", "GP Partner", "ST3"]

    ethnicity_categories = ["White", "Black", "Asian", "Mixed", "Other"]
    ethnicity_probs = [0.75, 0.07, 0.10, 0.04, 0.04]

    clinician_id = 1

    for _, row in providers_df.iterrows():
        ptype = row["provider_type"]

        # Rough staffing levels: more clinicians at hospitals
        if ptype == "ACUTE_HOSPITAL":
            n_site_clinicians = rng.integers(80, 150)
        elif ptype == "GP_PRACTICE":
            n_site_clinicians = rng.integers(8, 20)
        elif ptype == "COMMUNITY_CLINIC":
            n_site_clinicians = rng.integers(15, 40)
        elif ptype == "URGENT_CARE":
            n_site_clinicians = rng.integers(20, 50)
        elif ptype == "DIAGNOSTIC_CENTRE":
            n_site_clinicians = rng.integers(10, 25)
        else:
            n_site_clinicians = rng.integers(5, 15)

        roles = roles_by_type.get(ptype, ["Clinician"])

        for _ in range(n_site_clinicians):
            role = rng.choice(roles)
            specialty = rng.choice(specialties)
            band = rng.choice(bands)
            sex = rng.choice(["F", "M"], p=[0.6, 0.4])
            ethnicity = rng.choice(ethnicity_categories, p=ethnicity_probs)
            fte = np.round(rng.uniform(0.4, 1.0), 2)

            start_year = int(rng.integers(2008, 2023))
            start_month = int(rng.integers(1, 13))
            start_day = int(rng.integers(1, 28))
            start_date = date(start_year, start_month, start_day)

            is_active = bool(rng.choice([True, False], p=[0.85, 0.15]))
            end_date = None
            if not is_active:
                end_year = int(rng.integers(start_year + 1, 2024))
                end_month = int(rng.integers(1, 13))
                end_day = int(rng.integers(1, 28))
                end_date = date(end_year, end_month, end_day)

            records.append(
                {
                    "clinician_id": clinician_id,
                    "clinician_code": f"CLN{clinician_id:06d}",
                    "provider_id": row["provider_id"],
                    "role": role,
                    "specialty": specialty,
                    "grade_band": band,
                    "sex": sex,
                    "ethnicity_ons": ethnicity,
                    "fte": fte,
                    "start_date": start_date,
                    "end_date": end_date,
                    "is_active": is_active,
                }
            )
            clinician_id += 1

    return pd.DataFrame(records)
