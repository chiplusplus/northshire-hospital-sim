"""
EHR Diagnoses generator.

Attaches ICD-10 coded diagnoses to encounters. Separate from diagnostics.py
which generates S3-exported diagnostic test orders/results.
"""

import numpy as np
import pandas as pd


# Common ICD-10 codes relevant to a GM Trust
# NOTE: UK NHS ICD-10 uses NO decimal points (unlike US ICD-10-CM)
# Short codes padded with X (e.g. R51X not R51)
ICD10_CODES = [
    ("I10X", "Essential (primary) hypertension"),
    ("E119", "Type 2 diabetes mellitus without complications"),
    ("J459", "Asthma, unspecified"),
    ("J441", "Chronic obstructive pulmonary disease with acute exacerbation"),
    ("F411", "Generalized anxiety disorder"),
    ("F329", "Major depressive disorder, single episode, unspecified"),
    ("I251", "Atherosclerotic heart disease of native coronary artery"),
    ("M545", "Low back pain"),
    ("J069", "Acute upper respiratory infection, unspecified"),
    ("K210", "Gastro-oesophageal reflux disease with oesophagitis"),
    ("N390", "Urinary tract infection, site not specified"),
    ("R104", "Other and unspecified abdominal pain"),
    ("G439", "Migraine, unspecified"),
    ("L309", "Dermatitis, unspecified"),
    ("R51X", "Headache"),
    ("J189", "Pneumonia, unspecified organism"),
    ("S525", "Fracture of lower end of radius"),
    ("K590", "Constipation"),
    ("R079", "Chest pain, unspecified"),
    ("E785", "Hyperlipidaemia, unspecified"),
]


def generate_diagnoses(
    encounters_df: pd.DataFrame,
    seed: int,
) -> pd.DataFrame:
    """
    Generate EHR diagnosis records attached to encounters.

    Each encounter gets 0-3 diagnoses (first is PRIMARY, rest SECONDARY).
    """
    rng = np.random.default_rng(seed)
    records: list[dict] = []

    for _, enc in encounters_df.iterrows():
        # ~70% of encounters get at least one diagnosis
        n_diag = rng.choice([0, 1, 2, 3], p=[0.30, 0.45, 0.20, 0.05])
        if n_diag == 0:
            continue

        enc_date = pd.to_datetime(enc["encounter_datetime_start"])

        for i in range(n_diag):
            code_idx = int(rng.integers(0, len(ICD10_CODES)))
            code, desc = ICD10_CODES[code_idx]

            # Clinical datetime = encounter date
            clinical_dt = enc_date
            # Coded datetime = 0-7 days after encounter (coding lag)
            coded_dt = enc_date + pd.Timedelta(days=int(rng.integers(0, 8)))

            records.append({
                "patient_id": enc["patient_id"],
                "encounter_id": enc["encounter_id"],
                "diagnosis_code": code,
                "diagnosis_desc": desc,
                "diagnosis_type": "PRIMARY" if i == 0 else "SECONDARY",
                "coded_datetime": coded_dt,
                "clinical_datetime": clinical_dt,
                "source_system": "EHR",
            })

    df = pd.DataFrame(records)
    if not df.empty:
        df.insert(0, "diagnosis_id", range(1, len(df) + 1))
    else:
        df = pd.DataFrame(columns=[
            "diagnosis_id", "patient_id", "encounter_id",
            "diagnosis_code", "diagnosis_desc", "diagnosis_type",
            "coded_datetime", "clinical_datetime", "source_system",
        ])
    return df
