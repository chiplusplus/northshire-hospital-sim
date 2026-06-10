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
from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta
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
from northshire_sim.exports.simulation_queue import build_simulation_queue


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


HOLDBACK_DAYS = 12


def _default_start() -> date:
    return date.today() - relativedelta(months=12)


def _default_end() -> date:
    return date.today() + timedelta(days=HOLDBACK_DAYS)


DEFAULTS = GenerationConfig(
    seed=42,
    n_patients=100_000,
    n_providers=125,
    start_date=_default_start(),
    end_date=_default_end(),
    appointment_export_days=((_default_end() - _default_start()).days + 1),
    diagnostics_export_days=((_default_end() - _default_start()).days + 1),
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
    patients = generate_patients(
        cfg.n_patients,
        seed=cfg.seed,
        analysis_date=datetime.combine(cfg.end_date, datetime.min.time()),
    )
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
    # Immediate-only: export dates up to today (holdback days handled by simulation queue)
    cutoff = min(cfg.end_date, date.today())
    n_immediate_days = (cutoff - cfg.start_date).days + 1
    export_dates = [cfg.start_date + timedelta(days=i) for i in range(n_immediate_days)]

    appointment_artifacts = build_appointment_exports(
        encounters_df=dfs["encounters"],
        patients_df=dfs["patients"],
        export_dates=export_dates,
        seed=cfg.seed,
    )

    # Diagnostics: immediate-only (up to today)
    diag_df = dfs["diagnostics"].copy()
    if not diag_df.empty:
        diag_df["request_date"] = pd.to_datetime(diag_df["request_date"]).dt.date
        diag_df = diag_df[(diag_df["request_date"] >= cfg.start_date) & (diag_df["request_date"] <= cutoff)]

    diagnostics_artifacts = build_diagnostic_orders_exports(diag_df)

    # Provider reference Excel (single artifact)
    provider_excel = build_provider_reference_excel_artifact(
        providers_df=dfs["providers"],
        seed=cfg.seed,
    )

    return [*appointment_artifacts, *diagnostics_artifacts, provider_excel]


def _filter_to_cutoff(df: pd.DataFrame, date_col: str, cutoff: date) -> pd.DataFrame:
    """Keep only rows where date_col <= cutoff. Holdback rows go to the simulation queue."""
    filtered = df.copy()
    filtered[date_col] = pd.to_datetime(filtered[date_col])
    return filtered[filtered[date_col].dt.date <= cutoff]


def write_staging(dfs: Dict[str, pd.DataFrame], artifacts: List[ExportArtifact], staging_dir: Path) -> None:
    core_dir = staging_dir / "core"
    exports_dir = staging_dir / "exports"
    cutoff = date.today()

    # Core CSVs — filtered to exclude holdback days (those go to simulation queue only)
    write_csv(dfs["patients"], core_dir / "patients.csv")
    write_csv(dfs["providers"], core_dir / "providers.csv")
    write_csv(dfs["clinicians"], core_dir / "clinicians.csv")
    write_csv(_filter_to_cutoff(dfs["encounters"], "encounter_datetime_start", cutoff), core_dir / "encounters.csv")
    write_csv(_filter_to_cutoff(dfs["referrals"], "referral_datetime", cutoff), core_dir / "referrals.csv")
    write_csv(_filter_to_cutoff(dfs["diagnoses"], "clinical_datetime", cutoff), core_dir / "diagnoses.csv")
    write_csv(_filter_to_cutoff(dfs["diagnostics"], "request_date", cutoff), core_dir / "diagnostics.csv")
    write_csv(_filter_to_cutoff(dfs["urgent_care"], "arrival_datetime", cutoff), core_dir / "urgent_care_logs.csv")

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

    if staging_dir.exists():
        import shutil
        shutil.rmtree(staging_dir)
        print(f"\nCleared existing staging: {staging_dir}")

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

    # Build simulation queue (holdback days)
    print("\nBuilding simulation queue...")
    cutoff = date.today()
    sim_queue = build_simulation_queue(
        encounters_df=dfs["encounters"],
        referrals_df=dfs["referrals"],
        diagnoses_df=dfs["diagnoses"],
        urgent_care_df=dfs["urgent_care"],
        diagnostics_df=dfs["diagnostics"],
        patients_df=dfs["patients"],
        cutoff_date=cutoff,
        seed=cfg.seed,
    )
    print(f"Simulation queue: {len(sim_queue)} days staged")

    # Write simulation queue CSVs to local staging for publish script to upload
    sim_queue_dir = staging_dir / "simulation_queue"
    for day, files in sorted(sim_queue.items()):
        day_dir = sim_queue_dir / f"day={day.isoformat()}"
        day_dir.mkdir(parents=True, exist_ok=True)
        for filename, df in files.items():
            df.to_csv(day_dir / filename, index=False)

    print(f"  written to: {sim_queue_dir.resolve()}")

    print("\nDone.")


if __name__ == "__main__":
    main()
