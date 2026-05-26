from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from northshire_sim.publishing.db import FullRefreshConfig, full_refresh_mirror


# -------------------------
# Table sets
# -------------------------

DEFAULT_EHR_TABLES: Sequence[str] = (
    "patient_demographics",
    "encounters",
    "referrals",
    "diagnoses",
    "procedures",
)

DEFAULT_URGENT_TABLES: Sequence[str] = (
    "urgent_care_logs",
)


# -------------------------
# Configs
# -------------------------

@dataclass(frozen=True)
class MirrorRefreshConfig:
    """
    Generic mirror refresh config for a source system.

    internal_dsn: SQLAlchemy DSN for internal DB
    mirror_dsn:   SQLAlchemy DSN for mirror DB
    """
    internal_dsn: str
    mirror_dsn: str
    tables: Sequence[str]

    # Copy tuning
    read_chunksize: int = 50_000
    write_chunksize: int = 1_000

    # Schema + permissions scripts
    mirror_schema_sql_path: Path = Path()
    mirror_readonly_sql_path: Path = Path()


def refresh_ehr_mirror(
    *,
    internal_dsn: str,
    mirror_dsn: str,
    tables: Sequence[str] = DEFAULT_EHR_TABLES,
    read_chunksize: int = 50_000,
    write_chunksize: int = 1_000,
    mirror_schema_sql_path: Path = Path("sql/ehr/init.sql"),
    mirror_readonly_sql_path: Path = Path("sql/ehr/init_mirror_readonly.sql"),
) -> None:
    """
    Full refresh of the EHR mirror.
    """
    print("Refreshing EHR mirror...")

    full_refresh_mirror(
        internal_dsn=internal_dsn,
        mirror_dsn=mirror_dsn,
        cfg=FullRefreshConfig(
            schema_sql_path=mirror_schema_sql_path,
            readonly_sql_path=mirror_readonly_sql_path,
            tables=list(tables),
            read_chunksize=read_chunksize,
            write_chunksize=write_chunksize,
        ),
    )

    print("✅ EHR mirror refresh complete.")


def refresh_urgent_care_mirror(
    *,
    internal_dsn: str,
    mirror_dsn: str,
    tables: Sequence[str] = DEFAULT_URGENT_TABLES,
    read_chunksize: int = 50_000,
    write_chunksize: int = 1_000,
    mirror_schema_sql_path: Path = Path("sql/urgent_care/init.sql"),
    mirror_readonly_sql_path: Path = Path("sql/urgent_care/init_mirror_readonly.sql"),
) -> None:
    """
    Full refresh of the Urgent Care mirror.
    """
    print("Refreshing Urgent Care mirror...")

    full_refresh_mirror(
        internal_dsn=internal_dsn,
        mirror_dsn=mirror_dsn,
        cfg=FullRefreshConfig(
            schema_sql_path=mirror_schema_sql_path,
            readonly_sql_path=mirror_readonly_sql_path,
            tables=list(tables),
            read_chunksize=read_chunksize,
            write_chunksize=write_chunksize,
        ),
    )

    print("✅ Urgent Care mirror refresh complete.")


def refresh_all_mirrors(
    *,
    ehr_internal_dsn: str,
    ehr_mirror_dsn: str,
    urgent_internal_dsn: str,
    urgent_mirror_dsn: str,
) -> None:
    """
    Convenience: refresh both mirrors in sequence.
    Useful for scripts/trust.py.
    """
    refresh_ehr_mirror(internal_dsn=ehr_internal_dsn, mirror_dsn=ehr_mirror_dsn)
    refresh_urgent_care_mirror(internal_dsn=urgent_internal_dsn, mirror_dsn=urgent_mirror_dsn)
