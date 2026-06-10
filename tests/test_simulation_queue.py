"""Tests for the simulation queue builder."""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from northshire_sim.exports.simulation_queue import build_simulation_queue

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

CUTOFF = date(2026, 5, 28)
DAY_BEFORE = date(2026, 5, 27)
DAY_AFTER_1 = date(2026, 5, 29)
DAY_AFTER_2 = date(2026, 5, 30)


def _make_patients() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "patient_id": ["P001", "P002"],
            "nhs_pseudo_id": ["NHS001", "NHS002"],
            "registered_gp_practice_id": ["GP01", "GP02"],
            "imd_decile": [3, 7],
        }
    )


def _make_encounters(dates: list[date]) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(dates):
        dt = datetime(d.year, d.month, d.day, 9, 0)
        rows.append(
            {
                "encounter_id": f"ENC{i:03d}",
                "patient_id": "P001",
                "provider_id": "PROV01",
                "clinician_id": "CLIN01",
                "encounter_datetime_start": dt,
                "encounter_datetime_end": dt.replace(hour=10),
                "encounter_type": "GP",
                "source_system": "APPOINTMENT",
                "was_attended": 1,
                "priority": "ROUTINE",
                "wait_time_days": 5,
            }
        )
    return pd.DataFrame(rows)


def _make_referrals(dates: list[date]) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(dates):
        rows.append(
            {
                "referral_id": f"REF{i:03d}",
                "patient_id": "P001",
                "referral_datetime": datetime(d.year, d.month, d.day, 11, 0),
            }
        )
    return pd.DataFrame(rows)


def _make_diagnoses(dates: list[date]) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(dates):
        rows.append(
            {
                "diagnosis_id": f"DX{i:03d}",
                "patient_id": "P001",
                "clinical_datetime": datetime(d.year, d.month, d.day, 12, 0),
            }
        )
    return pd.DataFrame(rows)


def _make_urgent_care(dates: list[date]) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(dates):
        rows.append(
            {
                "uc_log_id": f"UC{i:03d}",
                "patient_id": "P001",
                "arrival_datetime": datetime(d.year, d.month, d.day, 14, 0),
            }
        )
    return pd.DataFrame(rows)


def _make_diagnostics(dates: list[date]) -> pd.DataFrame:
    rows = []
    for i, d in enumerate(dates):
        rows.append(
            {
                "order_id": f"DIAG{i:03d}",
                "patient_id": "P001",
                "request_date": d,
            }
        )
    return pd.DataFrame(rows)


def _build_queue(
    dates: list[date],
    cutoff: date = CUTOFF,
) -> dict:
    return build_simulation_queue(
        encounters_df=_make_encounters(dates),
        referrals_df=_make_referrals(dates),
        diagnoses_df=_make_diagnoses(dates),
        urgent_care_df=_make_urgent_care(dates),
        diagnostics_df=_make_diagnostics(dates),
        patients_df=_make_patients(),
        cutoff_date=cutoff,
        seed=42,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_returns_only_holdback_days():
    """Only dates strictly after cutoff appear in the queue."""
    all_dates = [DAY_BEFORE, CUTOFF, DAY_AFTER_1, DAY_AFTER_2]
    queue = _build_queue(all_dates)

    assert DAY_BEFORE not in queue
    assert CUTOFF not in queue
    assert DAY_AFTER_1 in queue
    assert DAY_AFTER_2 in queue


def test_each_day_has_expected_files():
    """Each holdback day contains the core CSV files."""
    queue = _build_queue([DAY_AFTER_1])

    assert DAY_AFTER_1 in queue
    day_files = queue[DAY_AFTER_1]

    # These should always be present given we supply data for that day
    assert "encounters.csv" in day_files
    assert "referrals.csv" in day_files
    assert "diagnoses.csv" in day_files
    assert "urgent_care_logs.csv" in day_files
    assert "diagnostic_orders.csv" in day_files

    # appointments.csv present because encounters are GP + APPOINTMENT
    assert "appointments.csv" in day_files

    # Verify they are DataFrames with rows
    for name, df in day_files.items():
        assert isinstance(df, pd.DataFrame), f"{name} is not a DataFrame"
        assert len(df) > 0, f"{name} is empty"


def test_empty_holdback_returns_empty_dict():
    """If all data is before/on cutoff, returns empty dict."""
    queue = _build_queue([DAY_BEFORE, CUTOFF])
    assert queue == {}
