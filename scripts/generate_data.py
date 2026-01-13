"""
Master synthetic data generator for:
- Patients
- Providers / Sites
- Clinicians
- Encounters
- Referrals
- Diagnostics

This script wires everything together and ensures IDs / FKs are consistent.
"""

from pathlib import Path
from datetime import date, timedelta

import pandas as pd

# --- import your existing generators here ---
from generators.helpers.patients import generate_patients
from generators.helpers.providers import generate_providers
from generators.helpers.clinicians import generate_clinicians
from generators.helpers.encounters import generate_encounters
from generators.helpers.referrals import generate_referrals
from generators.helpers.diagnostics import generate_diagnostics, apply_diagnostics_quality_issues
from src.northshire_sim.exports.exports import build_appointment_export, build_diagnoses_export, build_site_info_export
from generators.helpers.urgent_care import (
    generate_urgent_care_logs,
    degrade_urgent_care_quality,
)
from static_exports.scripts.write_files_to_s3 import upload_exports_to_s3


# -------------------
# CONFIG
# -------------------

OUTPUT_DIR = Path("data/generated")  # e.g. data/raw/dev
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

N_PATIENTS = 100_000
N_PROVIDERS = 25          # tweak as you like
N_CLINICIANS = 400        # tweak as you like

ANALYSIS_START = date(2022, 1, 1)
ANALYSIS_END = date(2024, 12, 31)

GLOBAL_SEED = 42  # use for reproducibility


# -------------------
# UTILS
# -------------------

def set_pandas_options():
    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 50)


def save_df(df: pd.DataFrame, name: str, format: str = "csv") -> None:
    """
    Save a dataframe to OUTPUT_DIR with a consistent naming pattern.
    """
    path = OUTPUT_DIR / f"{name}.{format}"

    if format == "parquet":
        df.to_parquet(path, index=False)
    elif format == "csv":
        df.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported format: {format}")

    print(f"✅ Saved {name} -> {path} (rows={len(df)})")


# -------------------
# MAIN ORCHESTRATION
# -------------------

def main():
    set_pandas_options()

    print("=== Synthetic NHS inequality dataset generation ===")

    # 1) Patients
    print("\n[1/7] Generating patients...")
    patients_df = generate_patients(
        n_patients=N_PATIENTS,
        seed=GLOBAL_SEED,
    )
    # Ensure patient_id is unique and sorted
    patients_df = patients_df.sort_values("patient_id").reset_index(drop=True)
    save_df(patients_df, "patients")

    # 2) Providers / Sites
    print("\n[2/7] Generating providers / sites...")
    providers_df = generate_providers(
        n_providers=N_PROVIDERS,
        seed=GLOBAL_SEED + 1,
    )
    # Expect provider_id as PK
    providers_df = providers_df.sort_values("provider_id").reset_index(drop=True)
    save_df(providers_df, "providers")

    # 3) Clinicians
    print("\n[3/7] Generating clinicians...")
    clinicians_df = generate_clinicians(
        n_clinicians=N_CLINICIANS,
        providers_df=providers_df,
        seed=GLOBAL_SEED + 2,
    )
    # Expect clinician_id as PK, provider_id as FK
    save_df(clinicians_df, "clinicians")

    # 4) Encounters
    print("\n[4/7] Generating encounters...")
    encounters_df = generate_encounters(
        patients_df=patients_df,
        providers_df=providers_df,
        clinicians_df=clinicians_df,
        start_date=ANALYSIS_START,
        end_date=ANALYSIS_END,
        seed=GLOBAL_SEED + 3,
    )
    # Sanity checks on FKs
    assert encounters_df["patient_id"].isin(patients_df["patient_id"]).all(), \
        "Some encounter.patient_id not found in patients"
    assert encounters_df["provider_id"].isin(providers_df["provider_id"]).all(), \
        "Some encounter.provider_id not found in providers"
    assert encounters_df["clinician_id"].isin(clinicians_df["clinician_id"]).all(), \
        "Some encounter.clinician_id not found in clinicians"

    save_df(encounters_df, "encounters")

    # 5) Referrals
    print("\n[5/7] Generating referrals...")
    referrals_df = generate_referrals(
        patients_df=patients_df,
        providers_df=providers_df,
        analysis_start=ANALYSIS_START,
        analysis_end=ANALYSIS_END,
        seed=GLOBAL_SEED + 4,
    )
    # Sanity-check FKs
    if "patient_id" in referrals_df.columns:
        assert referrals_df["patient_id"].isin(patients_df["patient_id"]).all(), \
            "Some referral.patient_id not found in patients"
    if "encounter_id" in referrals_df.columns:
        assert referrals_df["encounter_id"].isin(encounters_df["encounter_id"]).all(), \
            "Some referral.encounter_id not found in encounters"

    save_df(referrals_df, "referrals")

    # 6) Diagnostics
    print("\n[6/7] Generating diagnostics...")
    diagnostics_df = generate_diagnostics(
        referrals_df=referrals_df,
        patients_df=patients_df,
        encounters_df=encounters_df,
        seed=GLOBAL_SEED + 5,
    )
    if "patient_id" in diagnostics_df.columns:
        assert diagnostics_df["patient_id"].isin(patients_df["patient_id"]).all(), \
            "Some diagnostics.patient_id not found in patients"
    if "encounter_id" in diagnostics_df.columns:
        # Only validate encounter_ids that are populated (non-null).
        mask = diagnostics_df["encounter_id"].notna()
        if mask.any():
            assert diagnostics_df.loc[mask, "encounter_id"].isin(
                encounters_df["encounter_id"]
            ).all(), \
                "Some diagnostics.encounter_id not found in encounters"
    diagnostics_df = apply_diagnostics_quality_issues(diagnostics_df, seed=GLOBAL_SEED + 5)

    save_df(diagnostics_df, "diagnostics")

    # 7) Urgent Care Logs
    print("\n[7/7] Generating urgent care logs...")
    urgent_logs_df = generate_urgent_care_logs(encounters_df, patients_df, providers_df, seed=99)
    urgent_logs_df = degrade_urgent_care_quality(urgent_logs_df, seed=GLOBAL_SEED + 6)
    
    if "patient_id" in urgent_logs_df.columns:
        assert urgent_logs_df["patient_id"].isin(patients_df["patient_id"]).all(), \
            "Some urgent_care.patient_id not found in patients"
    if "provider_id" in urgent_logs_df.columns:
        assert urgent_logs_df["provider_id"].isin(providers_df["provider_id"]).all(), \
            "Some urgent_care.provider_id not found in patients"
    
    save_df(urgent_logs_df, "urgent_care_logs")

    print("\n🎉 Done. All synthetic datasets generated in:", OUTPUT_DIR)

    # 7) Static Exports

    print("=== Export files generation ===")
    
    print("\n[1/3] Generating appointments csv...")
    start = date(2024, 12, 1)
    end = date(2024, 12, 31)

    current = start
    while current <= end:
        build_appointment_export(
            encounters_df=encounters_df,
            patients_df=patients_df,
            export_date=current,
            seed=GLOBAL_SEED + 7,
        )
        current += timedelta(days=1)

    print(f"✅ Generated urgent care logs exports for {start} to {end}")

    print("\n[2/3] Generating diagnostic orders csv...")
    build_diagnoses_export(
        diagnostics_df=diagnostics_df,
    )

    print("✅ Generated diagnostic orders exports")

    print("\n[3/3] Generating site information excel sheet...")
    build_site_info_export(
        providers_df=providers_df,
        seed=GLOBAL_SEED + 8,
    )

    print("✅ Generated site information excel sheet")
    
    print("=== Exporting files to required destination ===")

    print("\n[1/2] Uploading diagnostic orders to s3...")
    upload_exports_to_s3(
        local_dir= Path("static_exports") / "s3_trust" / "diagnostics_orders",
        bucket="northshire-trust-diagnostics-exports",
        prefix="diagnostics_orders/",
    )

    print("✅ Uploaded diagnostic orders to s3.")

    print("\n[2/2] Uploading providers reference file...")
    upload_exports_to_s3(
        local_dir= Path("static_exports") / "excel" / "sites_and_services_master.xlsx",
        bucket="northshire-trust-reference-data",
        prefix="providers/",
    )

    print("✅ Uploaded providers reference file to s3.")
    



if __name__ == "__main__":
    main()
