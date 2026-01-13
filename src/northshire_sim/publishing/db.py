import pandas as pd
import numpy as np
from psycopg2.extras import execute_values

def load_table(conn, df, table_name, columns):
    # Ensure object dtype so we can store None; replace NA/NaT with None
    df = df.astype(object).where(pd.notnull(df), None)

    def to_py(x):
        if x is None:
            return None
        # pandas Timestamp -> python datetime
        if isinstance(x, pd.Timestamp):
            return x.to_pydatetime()
        # numpy datetime64 -> python datetime
        if isinstance(x, np.datetime64):
            return pd.to_datetime(x).to_pydatetime()
        # numpy numeric scalars -> python builtins
        if isinstance(x, np.integer):
            return int(x)
        if isinstance(x, np.floating):
            return float(x)
        return x

    rows = [tuple(to_py(v) for v in row) for row in df.values.tolist()]
    sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES %s"

    with conn.cursor() as cur:
        execute_values(cur, sql, rows)
    conn.commit()


def truncate_tables(conn, table_names):
    # Truncate and reset serials for the provided tables
    if not table_names:
        return
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE TABLE {', '.join(table_names)} RESTART IDENTITY CASCADE;")
    conn.commit()