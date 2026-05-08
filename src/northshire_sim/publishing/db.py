from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Literal

import pandas as pd
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine


# -------------------------
# Engine / Connections
# -------------------------

def make_engine(dsn: str) -> Engine:
    """
    Create a SQLAlchemy engine for Postgres.
    pool_pre_ping avoids stale connections in longer-running scripts.
    """
    return create_engine(dsn, pool_pre_ping=True, future=True)


# -------------------------
# SQL execution
# -------------------------

def run_sql(engine: Engine, sql_text: str) -> None:
    """
    Execute SQL which may contain multiple statements, including DO $$ blocks.

    Why raw_connection + cursor?
    - SQLAlchemy's default execute expects single statements and can struggle with
      multi-statement scripts + DO $$ blocks.
    - Postgres can parse the full script correctly when sent as one string.
    """
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        try:
            cur.execute(sql_text)
        finally:
            cur.close()
        conn.commit()
    finally:
        conn.close()


def run_sql_file(engine: Engine, path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"SQL file not found: {path}")
    run_sql(engine, path.read_text(encoding="utf-8"))


# -------------------------
# Introspection
# -------------------------

def table_exists(engine: Engine, table_name: str, schema: str = "public") -> bool:
    insp = inspect(engine)
    return insp.has_table(table_name, schema=schema)


# -------------------------
# Truncate / Reset
# -------------------------

def truncate_tables(engine: Engine, tables: Iterable[str]) -> None:
    """
    Truncate tables and reset identity sequences.

    CASCADE is safe for this simulator and simplifies FK additions later.
    """
    with engine.begin() as conn:
        for t in tables:
            conn.execute(text(f'TRUNCATE TABLE "{t}" RESTART IDENTITY CASCADE;'))


# -------------------------
# Load helpers
# -------------------------

def load_df(
    engine: Engine,
    df: pd.DataFrame,
    table: str,
    *,
    if_exists: Literal["append", "replace", "fail"] = "append",
    chunksize: int = 1_000,
) -> int:
    """
    Bulk load a DataFrame into Postgres using pandas.to_sql.

    if_exists:
      - "append" (default): add rows
      - "replace": drop and recreate table (avoid for your internal schemas)
      - "fail": error if table exists

    Returns: number of rows written.
    """
    if df is None or df.empty:
        return 0

    df.to_sql(
        name=table,
        con=engine,
        if_exists=if_exists,
        index=False,
        method="multi",
        chunksize=chunksize,
    )
    return len(df)


def load_csv(
    engine: Engine,
    csv_path: Path,
    table: str,
    *,
    if_exists: Literal["append", "replace", "fail"] = "append",
    chunksize: int = 50_000,
    dtype: Optional[dict] = None,
    usecols: Optional[list[str]] = None,
) -> int:
    """
    Load a CSV into Postgres via pandas chunked reads.

    Useful when staging outputs are CSV and you don't want to materialise
    huge DataFrames in memory in one go.

    Args:
        engine: SQLAlchemy engine
        csv_path: Path to CSV file
        table: Target table name
        if_exists: "append", "replace", or "fail"
        chunksize: Rows per chunk
        dtype: Optional dtype dict
        usecols: Optional list of column names to keep. If provided, only these
                columns will be loaded from the CSV (others ignored).

    Returns: number of rows written.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    total = 0
    for chunk in pd.read_csv(csv_path, chunksize=chunksize, dtype=dtype, usecols=usecols):
        if chunk.empty:
            continue
        # first chunk: honour if_exists, then append for subsequent
        mode = if_exists if total == 0 else "append"
        total += load_df(engine, chunk, table, if_exists=mode, chunksize=min(1_000, chunksize))

    return total

# -------------------------
# Copy helpers (internal → mirror)
# -------------------------

def copy_table(
    internal_conn,
    mirror_conn,
    table_name: str,
    read_chunksize: int = 50_000,
    write_chunksize: int = 10_000,
):
    """Copy a table from internal to mirror with proper error handling."""
    query = f"SELECT * FROM {table_name}"
    
    total_rows = 0
    try:
        for chunk in pd.read_sql(query, internal_conn, chunksize=read_chunksize):
            try:
                chunk.to_sql(
                    table_name,
                    mirror_conn,
                    if_exists="append",
                    index=False,
                    chunksize=write_chunksize,
                )
                total_rows += len(chunk)
            except Exception as e:
                # Rollback the failed transaction
                mirror_conn.rollback()
                raise RuntimeError(f"Failed to write chunk to {table_name}: {e}") from e
    except Exception as e:
        mirror_conn.rollback()
        raise
    
    return total_rows


@dataclass(frozen=True)
class FullRefreshConfig:
    """
    Generic full refresh settings used by mirror refreshers.
    """
    schema_sql_path: Path
    readonly_sql_path: Optional[Path] = None
    tables: Optional[list[str]] = None
    read_chunksize: int = 50_000
    write_chunksize: int = 1_000


def full_refresh_mirror(
    *,
    internal_dsn: str,
    mirror_dsn: str,
    cfg: FullRefreshConfig,
) -> None:
    """
    Generic "ensure schema → truncate → copy → apply readonly" refresh.
    Works for both EHR and urgent care mirrors.
    """
    internal = make_engine(internal_dsn)
    mirror = make_engine(mirror_dsn)

    try:
        # Ensure schema exists
        run_sql_file(mirror, cfg.schema_sql_path)

        if not cfg.tables:
            raise ValueError("cfg.tables must be provided for full_refresh_mirror()")

        # Truncate then copy
        truncate_tables(mirror, cfg.tables)

        for t in cfg.tables:
            rows = copy_table(
                internal,
                mirror,
                t,
                read_chunksize=cfg.read_chunksize,
                write_chunksize=cfg.write_chunksize,
            )
            print(f"   - {t}: copied {rows:,} rows")

        # Apply readonly grants if configured
        if cfg.readonly_sql_path is not None:
            run_sql_file(mirror, cfg.readonly_sql_path)

    finally:
        internal.dispose()
        mirror.dispose()
