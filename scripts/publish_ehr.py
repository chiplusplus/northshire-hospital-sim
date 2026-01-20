from __future__ import annotations

import argparse

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import yaml

from northshire_sim.publishing.ehr import EhrPublishConfig, publish_ehr_internal
from northshire_sim.publishing.mirror import refresh_ehr_mirror


def load_sources(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"sources.yaml not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish EHR internal DB and refresh EHR mirror.")
    p.add_argument("--sources", type=str, default="config/sources.yaml", help="Path to sources.yaml")
    p.add_argument("--staging-core", type=str, default="data/staging/core", help="Core staging directory")
    p.add_argument("--init-sql", type=str, default="sql/ehr/init.sql", help="EHR init.sql path")
    p.add_argument("--truncate", action="store_true", help="Truncate target tables before loading")
    p.add_argument("--no-truncate", dest="truncate", action="store_false")
    p.set_defaults(truncate=True)
    p.add_argument("--csv-chunksize", type=int, default=50_000)
    p.add_argument("--read-chunksize", type=int, default=50_000, help="Mirror read chunksize")
    p.add_argument("--write-chunksize", type=int, default=10_000, help="Mirror write chunksize")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    sources = load_sources(Path(args.sources))

    pg = sources.get("postgres", {})
    ehr_internal_dsn = pg.get("ehr_internal_dsn")
    ehr_mirror_dsn = pg.get("ehr_mirror_dsn")

    if not ehr_internal_dsn or not ehr_mirror_dsn:
        raise KeyError(
            "Missing DSNs in sources.yaml under postgres:\n"
            "  - ehr_internal_dsn\n"
            "  - ehr_mirror_dsn"
        )

    # 1) Load internal
    publish_ehr_internal(
        EhrPublishConfig(
            internal_dsn=ehr_internal_dsn,
            staging_core_dir=Path(args.staging_core),
            init_sql_path=Path(args.init_sql),
            truncate_before_load=bool(args.truncate),
            csv_chunksize=int(args.csv_chunksize),
        )
    )

    # 2) Refresh mirror
    refresh_ehr_mirror(
        internal_dsn=ehr_internal_dsn,
        mirror_dsn=ehr_mirror_dsn,
        read_chunksize=int(args.read_chunksize),
        write_chunksize=int(args.write_chunksize),
        mirror_schema_sql_path=Path("sql/ehr/init.sql"),
        mirror_readonly_sql_path=Path("sql/ehr/init_mirror_readonly.sql"),
    )


if __name__ == "__main__":
    main()
