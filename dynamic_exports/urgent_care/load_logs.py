import pandas as pd
import numpy as np
import psycopg2
from datetime import datetime, timedelta
from dynamic_exports.helpers.helpers import load_table, truncate_tables

def main():
    # Always truncate target tables before loading to ensure overwrite behavior

    conn = psycopg2.connect(
        host="localhost",
        port=5434,
        dbname="uc",
        user="uc_user",
        password="uc_password",
    )

    urgent_logs = pd.read_csv(
        "data/generated/urgent_care_logs.csv",
        parse_dates=["arrival_datetime", "triage_datetime", "seen_by_clinician_datetime", "departure_datetime"],
    )

    # Always truncate (overwrite) before loading
    truncate_tables(conn, ["urgent_care_logs"])
    print("Truncated table urgent_care_logs")

    print(f"Loading urgent_care_logs ({len(urgent_logs)} rows)...")
    load_table(conn, urgent_logs, "urgent_care_logs", list(urgent_logs.columns))

    conn.close()

if __name__ == "__main__":
    main()
