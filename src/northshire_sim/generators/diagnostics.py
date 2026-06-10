"""
Diagnostics generator.

Generates diagnostic orders and results based on referrals and (optionally) encounters.
"""

import numpy as np
import pandas as pd

TEST_TYPES = ["bloods", "xray", "ct", "mri", "ecg", "ultrasound"]

TEST_PANELS_BY_TYPE = {
    "bloods": ["fbc", "lipids", "u_and_e", "lfts", "hba1c"],
    "xray": ["chest_xray", "limb_xray", "spine_xray"],
    "ct": ["ct_head", "ct_chest", "ct_abdomen"],
    "mri": ["mri_brain", "mri_spine", "mri_knee"],
    "ecg": ["resting_ecg", "stress_ecg"],
    "ultrasound": ["abdominal_ultrasound", "pelvic_ultrasound", "vascular_ultrasound"],
}


def _result_flag(chronic_count, specialty, rng: np.random.Generator):
    base = 0.8  # chance of normal
    if chronic_count >= 2:
        base -= 0.15
    if specialty in ["cardiology", "oncology", "respiratory"]:
        base -= 0.1

    base = max(0.4, base)
    r = rng.random()
    if r < base:
        return "normal"
    elif r < base + 0.15:
        return "abnormal"
    elif r < base + 0.18:
        return "critical"
    else:
        return "inconclusive"


def generate_diagnostics(referrals_df, patients_df, encounters_df, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    patients_idx = patients_df.set_index("patient_id")

    diag_rows = []

    # 1) Diagnostics from referrals
    for _, ref in referrals_df.iterrows():
        patient_id = ref["patient_id"]
        try:
            p = patients_idx.loc[patient_id]
        except KeyError:
            continue

        n_tests = rng.choice([0, 1, 2, 3], p=[0.1, 0.4, 0.35, 0.15])
        if n_tests == 0:
            continue

        request_dates = ref["referral_datetime"] + pd.to_timedelta(
            rng.integers(0, 30, size=n_tests), unit="D"
        )

        for rd in request_dates:
            test_type = rng.choice(TEST_TYPES)
            panel = rng.choice(TEST_PANELS_BY_TYPE[test_type])

            performed_offset = rng.integers(0, 21)
            performed_date = rd + pd.Timedelta(days=int(performed_offset))

            result_offset = rng.integers(0, 7)
            result_date = performed_date + pd.Timedelta(days=int(result_offset))

            result_flag = _result_flag(
                p.get("chronic_conditions_count", 0),
                ref.get("referral_specialty", ""),
                rng,
            )

            provider_id = ref["target_provider_id"]

            diag_rows.append(
                {
                    "patient_id": patient_id,
                    "referral_id": ref["referral_id"],
                    "encounter_id": None,
                    "provider_id": provider_id,
                    "test_type": test_type,
                    "test_panel": panel,
                    "request_date": rd,
                    "performed_date": performed_date,
                    "result_date": result_date,
                    "result_flag": result_flag,
                }
            )

    # 2) Optional diagnostics directly from encounters
    if encounters_df is not None:
        encounters_sample = encounters_df.sample(frac=0.4, replace=False, random_state=42)

        for _, enc in encounters_sample.iterrows():
            patient_id = enc["patient_id"]
            try:
                p = patients_idx.loc[patient_id]
            except KeyError:
                continue

            n_tests = rng.choice([1, 2], p=[0.7, 0.3])

            for _ in range(n_tests):
                test_type = rng.choice(TEST_TYPES)
                panel = rng.choice(TEST_PANELS_BY_TYPE[test_type])

                enc_date = pd.to_datetime(enc["encounter_datetime_start"])
                request_date = enc_date + pd.Timedelta(days=int(rng.integers(-1, 2)))

                performed_offset = rng.integers(0, 3)
                performed_date = request_date + pd.Timedelta(days=int(performed_offset))

                result_offset = rng.integers(0, 5)
                result_date = performed_date + pd.Timedelta(days=int(result_offset))

                result_flag = _result_flag(
                    p.get("chronic_conditions_count", 0),
                    enc.get("encounter_specialty", ""),
                    rng,
                )

                diag_rows.append(
                    {
                        "patient_id": patient_id,
                        "referral_id": None,
                        "encounter_id": enc["encounter_id"],
                        "provider_id": enc["provider_id"],
                        "test_type": test_type,
                        "test_panel": panel,
                        "request_date": request_date,
                        "performed_date": performed_date,
                        "result_date": result_date,
                        "result_flag": result_flag,
                    }
                )

    diagnostics_df = pd.DataFrame(diag_rows)
    diagnostics_df.insert(0, "diagnostic_id", range(1, len(diagnostics_df) + 1))
    return diagnostics_df
