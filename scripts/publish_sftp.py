#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def copy_files(src_glob: str, dst_dir: Path) -> int:
    ensure_dir(dst_dir)
    count = 0
    for f in sorted(Path().glob(src_glob)):
        if f.is_file():
            shutil.copy2(f, dst_dir / f.name)
            count += 1
    return count


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Publish staged exports to local SFTP drop folder.")
    p.add_argument("--staging-exports", type=str, default="data/staging/exports", help="Exports staging dir")
    p.add_argument("--sftp-drop", type=str, default="data/sftp_drop/outbound", help="Local SFTP outbound root")
    p.add_argument("--include-provider-excel", action="store_true", help="Also publish provider excel to SFTP")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    staging_exports = Path(args.staging_exports)
    outbound_root = Path(args.sftp_drop)

    appt_src = staging_exports / "appointments" / "*_appointments.csv"
    gp_src = staging_exports / "gp_registrations" / "*_gp_registrations.csv"
    esr_src = staging_exports / "esr" / "*_esr_*.csv"

    # Destination folders on the SFTP server
    appt_dst = outbound_root / "appointments"
    gp_dst = outbound_root / "gp_registrations"
    esr_dst = outbound_root / "esr"

    appt_n = copy_files(str(appt_src), appt_dst)

    gp_n = 0
    if (staging_exports / "gp_registrations").exists():
        gp_n = copy_files(str(gp_src), gp_dst)

    esr_n = 0
    if (staging_exports / "esr").exists():
        esr_n = copy_files(str(esr_src), esr_dst)

    provider_n = 0
    if args.include_provider_excel:
        provider_src = staging_exports / "providers" / "sites_and_services_master.xlsx"
        if provider_src.exists():
            provider_dst = outbound_root / "provider_reference"
            ensure_dir(provider_dst)
            shutil.copy2(provider_src, provider_dst / provider_src.name)
            provider_n = 1

    print("✅ Published to SFTP outbound drop:")
    print(f"  appointments: {appt_n} files → {appt_dst}")
    print(f"  gp_registrations: {gp_n} files → {gp_dst}")
    print(f"  esr: {esr_n} files → {esr_dst}")
    if args.include_provider_excel:
        print(f"  provider_excel: {provider_n} file → {outbound_root / 'provider_reference'}")


if __name__ == "__main__":
    main()
