"""
Exports builder. This module builds “files/feeds” from generated DataFrames.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Literal, Optional, Union

import numpy as np
import pandas as pd
from faker import Faker

fake = Faker("en_GB")


# -----------------------------
# Export artifact structures
# -----------------------------

ExportFormat = Literal["csv", "xlsx"]

@dataclass(frozen=True)
class ExportArtifact:
    """
    Represents a “would-be file” built from DataFrames.

    - relative_path: where the publisher should write it (e.g. appointments/20250101_appointments.csv)
    - format: csv/xlsx
    - payload: DataFrame (for csv) or dict of sheets (for xlsx)
    """
    relative_path: Path
    format: ExportFormat
    payload: Union[pd.DataFrame, Dict[str, pd.DataFrame]]


# -----------------------------
# Appointments (SFTP nightly CSV)
# -----------------------------

def build_appointment_export_df(
    encounters_df: pd.DataFrame,
    patients_df: pd.DataFrame,
    export_date: date,
    seed: int,
) -> pd.DataFrame:
    """
    Simulate the nightly incremental appointments CSV dropped by the booking system.

    Returns an export DataFrame.
    """
    rng = np.random.default_rng(seed)

    encounters_df = encounters_df.copy()
    encounters_df["encounter_datetime_start"] = pd.to_datetime(encounters_df["encounter_datetime_start"])

    mask = (
        (encounters_df["source_system"] == "APPOINTMENT")
        & (encounters_df["encounter_type"].isin(["GP", "OP"]))
        & (encounters_df["encounter_datetime_start"].dt.date == export_date)
    )

    appt = encounters_df.loc[mask].copy()
    if appt.empty:
        # Return empty with expected columns so downstream doesn’t break
        return pd.DataFrame(columns=[
            "appointment_id",
            "patient_id",
            "nhs_pseudo_id",
            "registered_gp_practice_id",
            "service_location_id",
            "clinician_id",
            "appointment_start_datetime",
            "appointment_end_datetime",
            "appointment_type",
            "mode",
            "slot_type",
            "booking_status",
            "booking_created_datetime",
            "booking_updated_datetime",
            "wait_time_days",
            "imd_decile",
        ])

    # Join to patients to get pseudo ID + GP practice
    appt = appt.merge(
        patients_df[["patient_id", "nhs_pseudo_id", "registered_gp_practice_id", "imd_decile"]],
        on="patient_id",
        how="left",
    )

    # Booking status (continuity with was_attended)
    booking_statuses = ["BOOKED", "ATTENDED", "DNA", "CANCELLED"]
    attended_mask = appt["was_attended"] == 1
    booking_probs = np.where(
        np.array(attended_mask)[:, None],
        [0.0, 0.98, 0.0, 0.02],
        [0.1, 0.0, 0.8, 0.1],
    )
    appt["booking_status"] = [rng.choice(booking_statuses, p=prob) for prob in booking_probs]

    # Mode and slot type (continuity with priority)
    appt["mode"] = np.where(
        appt["priority"] == "EMERGENCY",
        "F2F",
        rng.choice(["F2F", "TELEPHONE", "VIDEO"], size=len(appt), p=[0.7, 0.25, 0.05]),
    )

    appt["slot_type"] = np.where(
        appt["priority"] == "EMERGENCY",
        "URGENT",
        rng.choice(["ROUTINE", "URGENT"], size=len(appt), p=[0.85, 0.15]),
    )

    # Booking created/updated timestamps
    appt["booking_created_datetime"] = (
        appt["encounter_datetime_start"]
        - appt["wait_time_days"].clip(lower=0).apply(lambda d: timedelta(days=int(d)))
    )

    random_update_offset = rng.integers(0, 8, size=len(appt))
    appt["booking_updated_datetime"] = appt["booking_created_datetime"] + pd.to_timedelta(random_update_offset, unit="D")

    # Rename / reshape columns to look like a booking system
    export_df = appt.rename(
        columns={
            "encounter_id": "appointment_id",
            "encounter_datetime_start": "appointment_start_datetime",
            "encounter_datetime_end": "appointment_end_datetime",
            "encounter_type": "appointment_type",
            "provider_id": "service_location_id",
        }
    )

    export_columns = [
        "appointment_id",
        "patient_id",
        "nhs_pseudo_id",
        "registered_gp_practice_id",
        "service_location_id",
        "clinician_id",
        "appointment_start_datetime",
        "appointment_end_datetime",
        "appointment_type",
        "mode",
        "slot_type",
        "booking_status",
        "booking_created_datetime",
        "booking_updated_datetime",
        "wait_time_days",
        "imd_decile",
    ]
    export_df = export_df[export_columns]

    return export_df


def build_appointment_exports(
    encounters_df: pd.DataFrame,
    patients_df: pd.DataFrame,
    export_dates: List[date],
    seed: int,
    filename_template: str = "{yyyymmdd}_appointments.csv",
    relative_dir: Path = Path("appointments"),
) -> List[ExportArtifact]:
    """
    Build many nightly appointment CSV exports.
    """
    artifacts: List[ExportArtifact] = []
    for d in export_dates:
        df = build_appointment_export_df(encounters_df, patients_df, export_date=d, seed=seed)
        yyyymmdd = d.strftime("%Y%m%d")
        rel = relative_dir / filename_template.format(yyyymmdd=yyyymmdd)
        artifacts.append(ExportArtifact(relative_path=rel, format="csv", payload=df))
    return artifacts


# -----------------------------
# Diagnostics orders (S3 daily CSV exports)
# -----------------------------

def build_diagnostic_orders_exports(
    diagnostics_df: pd.DataFrame,
    relative_dir: Path = Path("diagnostics"),
    filename_template: str = "{yyyymmdd}_diagnostic_orders.csv",
) -> List[ExportArtifact]:
    """
    Build daily diagnostics order CSV exports grouped by request_date.
    """
    df = diagnostics_df.copy()
    if df.empty:
        return []

    df["request_date"] = pd.to_datetime(df["request_date"]).dt.date

    artifacts: List[ExportArtifact] = []
    for day, day_df in df.groupby("request_date"):
        yyyymmdd = str(day).replace("-", "")
        rel = relative_dir / filename_template.format(yyyymmdd=yyyymmdd)
        artifacts.append(ExportArtifact(relative_path=rel, format="csv", payload=day_df.reset_index(drop=True)))

    return artifacts


# -----------------------------
# Provider/site reference (Excel)
# -----------------------------

def build_provider_reference_df(providers_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """
    Shape providers_df into a realistic Trust-controlled “sites and services master”
    reference sheet.
    """
    rng = np.random.default_rng(seed)
    df = providers_df.copy()

    # Rename / align some columns to what a business-owned sheet might use
    df["site_name"] = df["provider_name"]

    # Mark main sites – e.g. first acute as 'main'
    df["is_main_site"] = False
    acute_mask = df["provider_type"] == "ACUTE_HOSPITAL"
    if acute_mask.any():
        first_acute_idx = df[acute_mask].index[0]
        df.loc[first_acute_idx, "is_main_site"] = True

    # Site status – mostly ACTIVE, with a few CLOSED or MERGED (includes messy value)
    df["site_status"] = np.where(
        df["is_active"],
        rng.choice(["ACTIVE", "MEASURED"], p=[0.9, 0.1], size=len(df)),
        rng.choice(["TEMP_CLOSED", "CLOSED", "MERGED"], p=[0.05, 0.8, 0.15], size=len(df)),
    )

    # ED + inpatient flags
    df["has_ed"] = df["provider_type"].isin(["URGENT_CARE", "ACUTE_HOSPITAL"])
    df["has_inpatient_beds"] = df["provider_type"].eq("ACUTE_HOSPITAL")

    # Size band (rough heuristic)
    df["size_band"] = np.where(
        df["provider_type"].eq("ACUTE_HOSPITAL"),
        rng.choice(["LARGE", "MEDIUM"], p=[0.7, 0.3], size=len(df)),
        rng.choice(["SMALL", "MEDIUM"], p=[0.8, 0.2], size=len(df)),
    )

    # Opening hours
    df["opening_hours"] = np.where(
        df["provider_type"].isin(["URGENT_CARE", "ACUTE_HOSPITAL"]),
        "24/7",
        rng.choice(["Mon-Fri 08:00-18:00", "Mon-Sat 09:00-17:00"], p=[0.75, 0.25], size=len(df)),
    )

    def service_lines_for_type(ptype: str) -> str:
        if ptype == "ACUTE_HOSPITAL":
            return "ED; Acute Medicine; Surgery; Diagnostics; Outpatients"
        if ptype == "GP_PRACTICE":
            return "Primary Care; Chronic Disease Management; Minor Procedures"
        if ptype == "COMMUNITY_CLINIC":
            return "Community Nursing; Rehab; Outpatient Therapy"
        if ptype == "URGENT_CARE":
            return "Urgent Care; Minor Injuries; Walk-in"
        if ptype == "DIAGNOSTIC_CENTRE":
            return "Imaging; Phlebotomy; Diagnostics"
        return "General Clinical Services"

    df["service_lines"] = df["provider_type"].apply(service_lines_for_type)

    # Site manager contact – realistic structure
    df["site_manager_name"] = [fake.name() for _ in range(len(df))]
    df["site_manager_email"] = [
        name.lower().replace(" ", ".") + "@northshire.nhs.uk"
        for name in df["site_manager_name"]
    ]

    # Reorder to look like a human-curated sheet
    columns_order = [
        "provider_id",
        "provider_code",
        "site_name",
        "provider_type",
        "parent_trust_name",
        "ics_region",
        "address_line_1",
        "city",
        "postcode",
        "postcode_sector",
        "lsoa_code",
        "is_main_site",
        "site_status",
        "has_ed",
        "has_inpatient_beds",
        "size_band",
        "opening_hours",
        "service_lines",
        "site_manager_name",
        "site_manager_email",
    ]

    return df[columns_order].copy()


def build_provider_reference_excel_artifact(
    providers_df: pd.DataFrame,
    seed: int,
    relative_path: Path = Path("providers") / "sites_and_services_master.xlsx",
    sheet_name: str = "sites_and_services",
) -> ExportArtifact:
    """
    Convenience wrapper: returns an Excel export artifact.
    Publisher decides how/where to write (S3 bucket, local cache, etc).
    """
    df = build_provider_reference_df(providers_df, seed=seed)
    return ExportArtifact(relative_path=relative_path, format="xlsx", payload={sheet_name: df})
