import pandas as pd
import psycopg2
from dynamic_exports.helpers.helpers import load_table, truncate_tables

def main():
    # Always truncate target tables before loading to ensure overwrite behavior

    conn = psycopg2.connect(
        host="localhost",
        port=5433,
        dbname="ehr",
        user="ehr_user",
        password="ehr_password",
    )

    patients = pd.read_csv("data/generated/patients.csv")
    encounters = pd.read_csv(
        "data/generated/encounters.csv",
        parse_dates=[
            "encounter_datetime_start",
            "encounter_datetime_end",
            "created_at",
        ],
    )

    tables = {
        "patient_demographics": (patients, list(patients.columns)),
        "encounters": (encounters, list(encounters.columns)),
    }

    # Always truncate (overwrite) before loading
    truncate_tables(conn, list(tables.keys()))
    print("Truncated tables:", ", ".join(tables.keys()))

    for table_name, (df, cols) in tables.items():
        print(f"Loading {table_name} ({len(df)} rows)...")
        load_table(conn, df, table_name, cols)

    conn.close()

if __name__ == "__main__":
    main()
