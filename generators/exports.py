from pathlib import Path
from datetime import date, timedelta
import numpy as np
import pandas as pd
from faker import Faker

sftp_output = Path("static_exports") / "sftp"
s3_output = Path("static_exports") / "s3_trust"
excel_output = Path("static_exports") / "excel"

################### SFTP APPOINTMENTS ###################

def build_appointment_export(
    encounters_df: pd.DataFrame,
    patients_df: pd.DataFrame,
    export_date: date,
    seed: int,
) -> None:
    """
    Simulate the nightly incremental appointments CSV dropped by the booking system.

    - Filters encounters to GP/OP appointments for the given export_date
      based on encounter start date.
    - Enriches with patient pseudo ID.
    - Adds booking-level fields (status, created/updated datetimes, mode, etc).

    Returns: Path to the written CSV file.
    """
    rng = np.random.default_rng(seed)

    # Ensure datetime dtype
    encounters_df = encounters_df.copy()
    encounters_df["encounter_datetime_start"] = pd.to_datetime(
        encounters_df["encounter_datetime_start"]
    )

    mask = (
        (encounters_df["source_system"] == "APPOINTMENT")
        & (encounters_df["encounter_type"].isin(["GP", "OP"]))
        & (encounters_df["encounter_datetime_start"].dt.date == export_date)
    )

    appt = encounters_df.loc[mask].copy()
    if appt.empty:
        print(f"No appointments found for {export_date}, skipping export.")
        return None

    # Join to patients to get pseudo ID + GP practice
    appt = appt.merge(
        patients_df[
            ["patient_id", "nhs_pseudo_id", "registered_gp_practice_id", "imd_decile"]
        ],
        on="patient_id",
        how="left",
    )

    # Booking status
    booking_statuses = ["BOOKED", "ATTENDED", "DNA", "CANCELLED"]
    # Assign booking probabilities per row based on was_attended
    attended_mask = appt["was_attended"] == 1
    booking_probs = np.where(
        np.array(attended_mask)[:, None],
        [0.0, 0.98, 0.0, 0.02],
        [0.1, 0.0, 0.8, 0.1]
    )
    # For each row, sample booking status using its probabilities
    appt["booking_status"] = [
        rng.choice(booking_statuses, p=prob) for prob in booking_probs
    ]

    # Mode and slot type
    appt["mode"] = np.where(
        appt["priority"] == "EMERGENCY",
        "F2F",
        rng.choice(
            ["F2F", "TELEPHONE", "VIDEO"],
            size=len(appt),
            p=[0.7, 0.25, 0.05])
    )

    appt["slot_type"] = np.where(
        appt["priority"] == "EMERGENCY",
        "URGENT",
        rng.choice(["ROUTINE", "URGENT"], size=len(appt), p=[0.85, 0.15]),
    )

    # Booking created/updated
    # Use wait_time_days to approximate creation date – earlier than appt
    appt["booking_created_datetime"] = (
        appt["encounter_datetime_start"]
        - appt["wait_time_days"].clip(lower=0).apply(lambda d: timedelta(days=int(d)))
    )

    # Updated time a bit after creation, maybe up to a week
    random_update_offset = rng.integers(0, 8, size=len(appt))
    appt["booking_updated_datetime"] = appt["booking_created_datetime"] + pd.to_timedelta(
        random_update_offset, unit="D"
    )

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

    # Build output path that mimics nightly SFTP drop
    out_path = sftp_output / "appointments" / f"{export_date:%Y%m%d}_appointments.csv"
    export_df.to_csv(out_path, index=False)
    print(f"Wrote appointment export: {out_path}")


################### S3 DIAGNOSES  ###################
def build_diagnoses_export(
    diagnostics_df: pd.DataFrame,
) -> None:

    df = diagnostics_df.copy()
    df["request_date"] = pd.to_datetime(df["request_date"]).dt.date

    for day, day_df in df.groupby("request_date"):
        day_str = str(day)

        file_path = s3_output / "diagnostics_orders" / f"{day_str.replace('-', '')}_diagnostic_orders.csv"
        day_df.to_csv(file_path, index=False)

################### EXCEL - sites info  ###################


def build_site_info_export(providers_df: pd.DataFrame, seed: int) -> pd.DataFrame:
    """
    Take the generated providers_df and shape it into a realistic 'site information'
    Excel sheet as maintained by the Trust.

    Returns the DataFrame and writes an .xlsx file to output_path.
    """
    rng = np.random.default_rng(seed)
    fake = Faker("en_GB")
    df = providers_df.copy()

    # Rename / align some columns to what a business-owned sheet might use
    df["site_name"] = df["provider_name"]

    # Mark main sites – e.g. first acute + first community as 'main'
    df["is_main_site"] = False
    acute_mask = df["provider_type"] == "ACUTE_HOSPITAL"
    if acute_mask.any():
        first_acute_idx = df[acute_mask].index[0]
        df.loc[first_acute_idx, "is_main_site"] = True

    # Site status – mostly ACTIVE, with a few CLOSED or MERGED
    df["site_status"] = np.where(
        df["is_active"],
        rng.choice(["ACTIVE", "MEASURED"], p=[0.9, 0.1], size=len(df)),  # typo-ish / messy value is realistic
        rng.choice(["TEMP_CLOSED", "CLOSED", "MERGED"], p=[0.05, 0.8, 0.15], size=len(df))
    )

    # Flags based on provider_type
    df["has_ed"] = False
    df["has_inpatient_beds"] = False

    df.loc[df["provider_type"] == "ACUTE_HOSPITAL", ["has_ed", "has_inpatient_beds"]] = [True, True]
    df.loc[df["provider_type"] == "URGENT_CARE", "has_ed"] = True

    # Simple size bands
    size_band_map = {
        "ACUTE_HOSPITAL": "District General Hospital",
        "GP_PRACTICE": "GP Practice",
        "COMMUNITY_CLINIC": "Community Site",
        "URGENT_CARE": "Urgent Care Centre",
        "DIAGNOSTIC_CENTRE": "Diagnostic Hub",
    }
    df["size_band"] = df["provider_type"].map(size_band_map).fillna("Other")

    # Opening hours – vary by type
    opening_hours = []
    for _, row in df.iterrows():
        ptype = row["provider_type"]
        if ptype in ["ACUTE_HOSPITAL", "URGENT_CARE"]:
            opening_hours.append("24/7")
        elif ptype == "GP_PRACTICE":
            opening_hours.append("08:00-18:30 Mon-Fri")
        elif ptype in ["COMMUNITY_CLINIC", "DIAGNOSTIC_CENTRE"]:
            opening_hours.append("09:00-17:00 Mon-Fri")
        else:
            opening_hours.append("09:00-17:00 Mon-Fri")
    df["opening_hours"] = opening_hours

    # Service lines – very rough, just enough for realism
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

    # Site manager contact – fake but realistic structure
    df["site_manager_name"] = [fake.name() for _ in range(len(df))]
    df["site_manager_email"] = [
    name.lower().replace(" ", ".") + "@northshire.nhs.uk"
    for name in df["site_manager_name"]
]

    # Reorder to look like a human-curated sheet
    columns_order = [
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

    site_info_df = df[columns_order]

    # Write to Excel – 
    site_info_df.to_excel(excel_output / "sites_and_services_master.xlsx", index=False)

    return site_info_df