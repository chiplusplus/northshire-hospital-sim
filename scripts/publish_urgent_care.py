#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
import yaml

from northshire_sim.publishing.urgent_care import UrgentCarePublishConfig, publish_urgent_care_internal
from northshire_sim.publishing.mirror import refresh_urgent_care_mirror


def load_sources(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"sources.yaml not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish urgent care internal DB and refresh urgent care mirror.")
    p.add_argument("--sources", type=str, default="config/sources.yaml", help="Path to sources.yaml")
    p.add_argument("--staging-core", type=str, default="data/staging/core", help="Core staging directory")
    p.add_argument("--init-sql", type=str, default="sql/urgent_care/init.sql", help="Urgent care init.sql path")
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
    urgent_internal_dsn = pg.get("urgent_internal_dsn")
    urgent_mirror_dsn = pg.get("urgent_mirror_dsn")

    if not urgent_internal_dsn or not urgent_mirror_dsn:
        raise KeyError(
            "Missing DSNs in sources.yaml under postgres:\n"
            "  - urgent_internal_dsn\n"
            "  - urgent_mirror_dsn"
        )

    # 1) Load internal
    publish_urgent_care_internal(
        UrgentCarePublishConfig(
            internal_dsn=urgent_internal_dsn,
            staging_core_dir=Path(args.staging_core),
            init_sql_path=Path(args.init_sql),
            truncate_before_load=bool(args.truncate),
            csv_chunksize=int(args.csv_chunksize),
        )
    )

    # 2) Refresh mirror
    refresh_urgent_care_mirror(
        internal_dsn=urgent_internal_dsn,
        mirror_dsn=urgent_mirror_dsn,
        read_chunksize=int(args.read_chunksize),
        write_chunksize=int(args.write_chunksize),
        mirror_schema_sql_path=Path("sql/urgent_care/init.sql"),
        mirror_readonly_sql_path=Path("sql/urgent_care/init_mirror_readonly.sql"),
    )


if __name__ == "__main__":
    main()
