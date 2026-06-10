from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from northshire_sim.publishing.db import make_engine, run_sql_file, truncate_tables, load_csv


URGENT_TABLES_IN_LOAD_ORDER = ("urgent_care_logs",)


@dataclass(frozen=True)
class UrgentCarePublishConfig:
    """
    Loads staged urgent care logs into the INTERNAL urgent care database (urgent_internal).
    """
    internal_dsn: str
    staging_core_dir: Path = Path("data/staging/core")
    init_sql_path: Path = Path("sql/urgent_care/init.sql")

    truncate_before_load: bool = True
    csv_chunksize: int = 50_000


def publish_urgent_care_internal(cfg: UrgentCarePublishConfig) -> None:
    """
    Load staged CSV into urgent_internal.

    Expected staging file:
      - urgent_care_logs.csv -> urgent_care_logs
    """
    engine = make_engine(cfg.internal_dsn)
    try:
        print("1) Ensuring Urgent Care internal schema exists...")
        run_sql_file(engine, cfg.init_sql_path)

        if cfg.truncate_before_load:
            print("2) Truncating Urgent Care internal tables...")
            truncate_tables(engine, URGENT_TABLES_IN_LOAD_ORDER)

        print("3) Loading urgent care logs from staging...")
        logs_csv = cfg.staging_core_dir / "urgent_care_logs.csv"

        n_rows = load_csv(
            engine,
            logs_csv,
            "urgent_care_logs",
            if_exists="append",
            chunksize=cfg.csv_chunksize,
            usecols=[
                "uc_log_id",
                "patient_id",
                "provider_id",
                "encounter_id",
                "arrival_datetime",
                "triage_datetime",
                "seen_by_clinician_datetime",
                "departure_datetime",
                "triage_category",
                "presenting_complaint",
                "outcome",
            ],
        )
        print(f"   - urgent_care_logs: loaded {n_rows:,} rows")

        print("✅ Urgent Care internal publish complete.")
    finally:
        engine.dispose()
