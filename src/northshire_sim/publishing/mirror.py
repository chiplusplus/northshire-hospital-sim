import subprocess
import os
from pathlib import Path

INTERNAL_URL = os.environ["EHR_INTERNAL_URL"]
MIRROR_URL = os.environ["EHR_MIRROR_URL"]

TABLES = [
    "public.patient_demographics",
    "public.encounters",
    "public.diagnoses",
    "public.procedures",
]

DUMP_PATH = Path("/tmp/ehr_mirror_dump.sql")

def run(cmd: list[str]):
    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr)
        raise RuntimeError("Command failed")

def main():
    # Dump selected tables
    run([
        "pg_dump",
        INTERNAL_URL,
        "--data-only",
        "--inserts",
        *sum([["-t", t] for t in TABLES], []),
        "-f",
        str(DUMP_PATH),
    ])

    # Reset mirror schema
    run([
        "psql",
        MIRROR_URL,
        "-c",
        "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    ])

    # Restore dump
    run(["psql", MIRROR_URL, "-f", str(DUMP_PATH)])

    # Re-apply readonly grants
    run([
        "psql",
        MIRROR_URL,
        "-f",
        "scripts/init_mirror_readonly.sql"
    ])

    print("Mirror refresh complete.")

if __name__ == "__main__":
    main()
