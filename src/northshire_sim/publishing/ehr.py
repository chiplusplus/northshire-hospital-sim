from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from northshire_sim.publishing.db import make_engine, run_sql_file, truncate_tables, load_csv


EHR_TABLES_IN_LOAD_ORDER = (
    "patient_demographics",
    "encounters",
    "referrals",
    "diagnoses",
    "procedures",
)


@dataclass(frozen=True)
class EhrPublishConfig:
    """
    Loads staged core outputs into the INTERNAL EHR database (ehr_internal).

    staging_core_dir: directory containing core CSVs produced by scripts/generate_data.py
    init_sql_path: schema DDL used to ensure tables exist in ehr_internal
    """
    internal_dsn: str
    staging_core_dir: Path = Path("data/staging/core")
    init_sql_path: Path = Path("sql/ehr/init.sql")

    truncate_before_load: bool = True
    csv_chunksize: int = 50_000


def publish_ehr_internal(cfg: EhrPublishConfig) -> None:
    """
    Load staged CSVs into ehr_internal.

    Expected staging files:
      - patients.csv -> patient_demographics
      - encounters.csv -> encounters

    Optional (only if you later stage these):
      - diagnoses.csv -> diagnoses
      - procedures.csv -> procedures
    """
    engine = make_engine(cfg.internal_dsn)
    try:
        print("1) Ensuring EHR internal schema exists...")
        run_sql_file(engine, cfg.init_sql_path)

        if cfg.truncate_before_load:
            print("2) Truncating EHR internal tables...")
            truncate_tables(engine, EHR_TABLES_IN_LOAD_ORDER)

        print("3) Loading core EHR tables from staging...")

        patients_csv = cfg.staging_core_dir / "patients.csv"
        encounters_csv = cfg.staging_core_dir / "encounters.csv"

        n_patients = load_csv(
            engine,
            patients_csv,
            "patient_demographics",
            if_exists="append",
            chunksize=cfg.csv_chunksize,
        )
        print(f"   - patient_demographics: loaded {n_patients:,} rows")

        n_enc = load_csv(
            engine,
            encounters_csv,
            "encounters",
            if_exists="append",
            chunksize=cfg.csv_chunksize,
        )
        print(f"   - encounters: loaded {n_enc:,} rows")

        referrals_csv = cfg.staging_core_dir / "referrals.csv"
        if referrals_csv.exists():
            n_ref = load_csv(
                engine, referrals_csv, "referrals",
                if_exists="append", chunksize=cfg.csv_chunksize,
            )
            print(f"   - referrals: loaded {n_ref:,} rows")
        else:
            print("   - referrals: no staging file found (skipping)")

        diagnoses_csv = cfg.staging_core_dir / "diagnoses.csv"
        if diagnoses_csv.exists():
            n_diag = load_csv(engine, diagnoses_csv, "diagnoses", if_exists="append", chunksize=cfg.csv_chunksize)
            print(f"   - diagnoses: loaded {n_diag:,} rows")
        else:
            print("   - diagnoses: no staging file found (skipping)")

        procedures_csv = cfg.staging_core_dir / "procedures.csv"
        if procedures_csv.exists():
            n_proc = load_csv(engine, procedures_csv, "procedures", if_exists="append", chunksize=cfg.csv_chunksize)
            print(f"   - procedures: loaded {n_proc:,} rows")
        else:
            print("   - procedures: no staging file found (skipping)")

        print("✅ EHR internal publish complete.")
    finally:
        engine.dispose()
