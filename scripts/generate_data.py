#!/usr/bin/env python3
"""
Generate synthetic Northshire Trust datasets into local staging.

Pipeline:
1) Generate core DataFrames via src/northshire_sim/generators/*
2) Validate dataset integrity via src/northshire_sim/checks/validate.py
3) Write core staging CSVs to data/staging/core/
4) Build export artifacts via src/northshire_sim/exports/exports.py
5) Write export artifacts to data/staging/exports/

Publishing (DB/S3/SFTP) is handled by scripts/publish_*.py.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd

# ---- generators (pure) ----
from northshire_sim.generators.patients import generate_patients
from northshire_sim.generators.providers import generate_providers
from northshire_sim.generators.clinicians import generate_clinicians
from northshire_sim.generators.encounters import generate_encounters
from northshire_sim.generators.referrals import generate_referrals
from northshire_sim.generators.diagnoses import generate_diagnoses
from northshire_sim.generators.diagnostics import generate_diagnostics
from northshire_sim.generators.urgent_care import generate_urgent_care_logs

# ---- validation (centralised) ----
from northshire_sim.checks.validate import validate_dataset

# ---- exports (pure transforms) ----
from northshire_sim.exports.exports import (
    ExportArtifact,
    build_appointment_exports,
    build_diagnostic_orders_exports,
    build_provider_reference_excel_artifact,
)


# -------------------------
# Config
# -------------------------

@dataclass(frozen=True)
class GenerationConfig:
    seed: int
    n_patients: int
    n_providers: int
    start_date: date
    end_date: date
    appointment_export_days: int
    diagnostics_export_days: int


DEFAULTS = GenerationConfig(
    seed=42,
    n_patients=100_000,
    n_providers=125,
    start_date=date(2023, 1, 1),
    end_date=date(2024, 12, 31),
    appointment_export_days=14,
    diagnostics_export_days=14,
)


# -------------------------
# Writers (staging IO only)
# -------------------------

def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_excel(sheets: Dict[str, pd.DataFrame], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def write_artifact(artifact: ExportArtifact, base_dir: Path) -> Path:
    out_path = base_dir / artifact.relative_path

    if artifact.format == "csv":
        assert isinstance(artifact.payload, pd.DataFrame)
        write_csv(artifact.payload, out_path)
    elif artifact.format == "xlsx":
        assert isinstance(artifact.payload, dict)
        write_excel(artifact.payload, out_path)
    else:
        raise ValueError(f"Unsupported export format: {artifact.format}")

    return out_path


def summarise(name: str, df: pd.DataFrame) -> None:
    print(f"{name:>12}: rows={len(df):>8,} cols={df.shape[1]:>3}")


# -------------------------
# Pipeline steps
# -------------------------

def generate_core(cfg: GenerationConfig) -> Dict[str, pd.DataFrame]:
    patients = generate_patients(cfg.n_patients, seed=cfg.seed)
    providers = generate_providers(cfg.n_providers, seed=cfg.seed)
    clinicians = generate_clinicians(providers_df=providers, seed=cfg.seed)

    encounters = generate_encounters(
        patients_df=patients,
        providers_df=providers,
        clinicians_df=clinicians,
        start_date=cfg.start_date,
        end_date=cfg.end_date,
        seed=cfg.seed,
    )

    referrals = generate_referrals(encounters_df=encounters, providers_df=providers, seed=cfg.seed)

    diagnoses = generate_diagnoses(
        encounters_df=encounters,
        seed=cfg.seed,
    )

    diagnostics = generate_diagnostics(
        referrals_df=referrals,
        patients_df=patients,
        encounters_df=encounters,
        seed=cfg.seed,
    )

    urgent_care = generate_urgent_care_logs(
        encounters_df=encounters,
        patients_df=patients,
        providers_df=providers,
        seed=cfg.seed,
    )

    dfs = {
        "patients": patients,
        "providers": providers,
        "clinicians": clinicians,
        "encounters": encounters,
        "referrals": referrals,
        "diagnoses": diagnoses,
        "diagnostics": diagnostics,
        "urgent_care": urgent_care,
    }

    validate_dataset(dfs)

    return dfs


def build_exports(cfg: GenerationConfig, dfs: Dict[str, pd.DataFrame]) -> List[ExportArtifact]:
    # Appointment nightly exports: last N days of the encounter window
    appt_end = cfg.end_date
    appt_start = appt_end - timedelta(days=cfg.appointment_export_days - 1)
    export_dates = [appt_start + timedelta(days=i) for i in range(cfg.appointment_export_days)]

    appointment_artifacts = build_appointment_exports(
        encounters_df=dfs["encounters"],
        patients_df=dfs["patients"],
        export_dates=export_dates,
        seed=cfg.seed,
    )

    # Diagnostics daily exports: last N days of request_date
    diag_df = dfs["diagnostics"].copy()
    if not diag_df.empty:
        diag_df["request_date"] = pd.to_datetime(diag_df["request_date"]).dt.date
        diag_start = cfg.end_date - timedelta(days=cfg.diagnostics_export_days - 1)
        diag_df = diag_df[(diag_df["request_date"] >= diag_start) & (diag_df["request_date"] <= cfg.end_date)]

    diagnostics_artifacts = build_diagnostic_orders_exports(diag_df)

    # Provider reference Excel (single artifact)
    provider_excel = build_provider_reference_excel_artifact(
        providers_df=dfs["providers"],
        seed=cfg.seed,
    )

    return [*appointment_artifacts, *diagnostics_artifacts, provider_excel]


def write_staging(dfs: Dict[str, pd.DataFrame], artifacts: List[ExportArtifact], staging_dir: Path) -> None:
    core_dir = staging_dir / "core"
    exports_dir = staging_dir / "exports"

    # Core CSVs
    write_csv(dfs["patients"], core_dir / "patients.csv")
    write_csv(dfs["providers"], core_dir / "providers.csv")
    write_csv(dfs["clinicians"], core_dir / "clinicians.csv")
    write_csv(dfs["encounters"], core_dir / "encounters.csv")
    write_csv(dfs["referrals"], core_dir / "referrals.csv")
    write_csv(dfs["diagnoses"], core_dir / "diagnoses.csv")
    write_csv(dfs["diagnostics"], core_dir / "diagnostics.csv")
    write_csv(dfs["urgent_care"], core_dir / "urgent_care_logs.csv")

    # Export artifacts (appointments/diagnostics/providers)
    written = [write_artifact(a, exports_dir) for a in artifacts]

    print(f"\n✅ Staging written:")
    print(f"  core:    {core_dir.resolve()}")
    print(f"  exports: {exports_dir.resolve()}")
    print(f"  wrote {len(written)} export artifacts")


# -------------------------
# CLI
# -------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate Northshire Trust synthetic datasets into staging.")
    p.add_argument("--seed", type=int, default=DEFAULTS.seed)
    p.add_argument("--n-patients", type=int, default=DEFAULTS.n_patients)
    p.add_argument("--n-providers", type=int, default=DEFAULTS.n_providers)
    p.add_argument("--start-date", type=str, default=str(DEFAULTS.start_date))
    p.add_argument("--end-date", type=str, default=str(DEFAULTS.end_date))
    p.add_argument("--appointment-export-days", type=int, default=DEFAULTS.appointment_export_days)
    p.add_argument("--diagnostics-export-days", type=int, default=DEFAULTS.diagnostics_export_days)
    p.add_argument("--staging-dir", type=str, default="data/staging")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    cfg = GenerationConfig(
        seed=args.seed,
        n_patients=args.n_patients,
        n_providers=args.n_providers,
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        appointment_export_days=args.appointment_export_days,
        diagnostics_export_days=args.diagnostics_export_days,
    )

    staging_dir = Path(args.staging_dir)

    print("\nGenerating core datasets...")
    dfs = generate_core(cfg)

    print("\nCore dataset summary:")
    for name, df in dfs.items():
        summarise(name, df)

    print("\nBuilding export artifacts...")
    artifacts = build_exports(cfg, dfs)
    print(f"Export artifacts built: {len(artifacts)}")

    print("\nWriting staging outputs...")
    write_staging(dfs, artifacts, staging_dir)

    print("\nDone.")


if __name__ == "__main__":
    main()
