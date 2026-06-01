"""Build per-day simulation queue slices from generated DataFrames.

Each day in the holdback window (dates > cutoff_date) gets a dict of
filename -> DataFrame, ready to be written as CSVs to the simulation queue.
"""

from __future__ import annotations

from datetime import date
from typing import Dict

import pandas as pd

from northshire_sim.exports.exports import build_appointment_export_df


def build_simulation_queue(
    *,
    encounters_df: pd.DataFrame,
    referrals_df: pd.DataFrame,
    diagnoses_df: pd.DataFrame,
    urgent_care_df: pd.DataFrame,
    diagnostics_df: pd.DataFrame,
    patients_df: pd.DataFrame,
    cutoff_date: date,
    seed: int,
) -> Dict[date, Dict[str, pd.DataFrame]]:
    """Split holdback data into per-day slices.

    Returns {date: {"encounters.csv": df, "referrals.csv": df, ...}}
    Only includes dates strictly after cutoff_date.
    Each file maps to one RDS table or S3/SFTP destination.
    """
    queue: Dict[date, Dict[str, pd.DataFrame]] = {}

    # Encounters
    enc = encounters_df.copy()
    enc["encounter_datetime_start"] = pd.to_datetime(enc["encounter_datetime_start"])
    enc["_biz_date"] = enc["encounter_datetime_start"].dt.date

    for day, day_enc in enc[enc["_biz_date"] > cutoff_date].groupby("_biz_date"):
        day_data = queue.setdefault(day, {})
        day_enc_clean = day_enc.drop(columns=["_biz_date"])

        # Appointments: GP/OP encounters via the same export builder
        appt_df = build_appointment_export_df(
            encounters_df=encounters_df,
            patients_df=patients_df,
            export_date=day,
            seed=seed,
        )
        if not appt_df.empty:
            day_data["appointments.csv"] = appt_df

        day_data["encounters.csv"] = day_enc_clean

    # Referrals
    ref = referrals_df.copy()
    ref["referral_datetime"] = pd.to_datetime(ref["referral_datetime"])
    ref["_biz_date"] = ref["referral_datetime"].dt.date

    for day, day_ref in ref[ref["_biz_date"] > cutoff_date].groupby("_biz_date"):
        day_data = queue.setdefault(day, {})
        day_data["referrals.csv"] = day_ref.drop(columns=["_biz_date"])

    # Diagnoses
    dx = diagnoses_df.copy()
    dx["clinical_datetime"] = pd.to_datetime(dx["clinical_datetime"])
    dx["_biz_date"] = dx["clinical_datetime"].dt.date

    for day, day_dx in dx[dx["_biz_date"] > cutoff_date].groupby("_biz_date"):
        day_data = queue.setdefault(day, {})
        day_data["diagnoses.csv"] = day_dx.drop(columns=["_biz_date"])

    # Urgent care logs
    uc = urgent_care_df.copy()
    uc["arrival_datetime"] = pd.to_datetime(uc["arrival_datetime"])
    uc["_biz_date"] = uc["arrival_datetime"].dt.date

    for day, day_uc in uc[uc["_biz_date"] > cutoff_date].groupby("_biz_date"):
        day_data = queue.setdefault(day, {})
        day_data["urgent_care_logs.csv"] = day_uc.drop(columns=["_biz_date"])

    # Diagnostics
    diag = diagnostics_df.copy()
    diag["request_date"] = pd.to_datetime(diag["request_date"]).dt.date

    for day, day_diag in diag[diag["request_date"] > cutoff_date].groupby(
        "request_date"
    ):
        day_data = queue.setdefault(day, {})
        day_data["diagnostic_orders.csv"] = day_diag

    return queue
