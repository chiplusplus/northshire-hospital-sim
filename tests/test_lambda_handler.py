"""Tests for the simulate_daily_drop Lambda handler."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add lambda directory to path so we can import the handler
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda"))

from simulate_daily_drop.handler import handler


def _base_event(**overrides):
    """Return a minimal event dict with sensible defaults."""
    event = {
        "trust_bucket": "test-trust-bucket",
        "queue_prefix": "_simulation_queue",
        "sftp_prefix": "sftp-incoming/outbound/appointments",
        "diagnostics_prefix": "diagnostics",
        "rds_dsn": "",
    }
    event.update(overrides)
    return event


@patch("simulate_daily_drop.handler._s3_client")
def test_no_queue_items_returns_noop(mock_s3_client):
    """When S3 list returns KeyCount=0, handler returns noop."""
    s3 = MagicMock()
    mock_s3_client.return_value = s3
    s3.list_objects_v2.return_value = {"KeyCount": 0, "Contents": []}

    result = handler(_base_event(), None)

    assert result["status"] == "noop"
    s3.list_objects_v2.assert_called_once_with(
        Bucket="test-trust-bucket",
        Prefix="_simulation_queue/day=",
    )


@patch("simulate_daily_drop.handler._s3_client")
def test_picks_earliest_day_and_deletes(mock_s3_client):
    """Given multiple days in queue, picks earliest, publishes, deletes consumed folder."""
    s3 = MagicMock()
    mock_s3_client.return_value = s3

    # First call: list all queue objects (returns two days)
    # Second call: list files in earliest day folder
    s3.list_objects_v2.side_effect = [
        {
            "KeyCount": 3,
            "Contents": [
                {"Key": "_simulation_queue/day=2024-01-15/appointments.csv"},
                {"Key": "_simulation_queue/day=2024-01-15/encounters.csv"},
                {"Key": "_simulation_queue/day=2024-01-20/appointments.csv"},
            ],
        },
        {
            "KeyCount": 2,
            "Contents": [
                {"Key": "_simulation_queue/day=2024-01-15/appointments.csv"},
                {"Key": "_simulation_queue/day=2024-01-15/encounters.csv"},
            ],
        },
    ]

    result = handler(_base_event(), None)

    assert result["status"] == "published"
    assert result["day"] == "2024-01-15"
    assert set(result["files"]) == {"appointments.csv", "encounters.csv"}

    # Verify delete_objects was called for the consumed day
    s3.delete_objects.assert_called_once_with(
        Bucket="test-trust-bucket",
        Delete={
            "Objects": [
                {"Key": "_simulation_queue/day=2024-01-15/appointments.csv"},
                {"Key": "_simulation_queue/day=2024-01-15/encounters.csv"},
            ]
        },
    )


@patch("simulate_daily_drop.handler._s3_client")
def test_publishes_appointments_to_sftp_prefix(mock_s3_client):
    """Verifies copy_object is called with the right SFTP destination key."""
    s3 = MagicMock()
    mock_s3_client.return_value = s3

    source_key = "_simulation_queue/day=2024-03-10/appointments.csv"

    s3.list_objects_v2.side_effect = [
        {
            "KeyCount": 1,
            "Contents": [{"Key": source_key}],
        },
        {
            "KeyCount": 1,
            "Contents": [{"Key": source_key}],
        },
    ]

    result = handler(
        _base_event(sftp_prefix="sftp-incoming/outbound/appointments"),
        None,
    )

    assert result["status"] == "published"

    s3.copy_object.assert_called_once_with(
        Bucket="test-trust-bucket",
        CopySource={"Bucket": "test-trust-bucket", "Key": source_key},
        Key="sftp-incoming/outbound/appointments/20240310_appointments.csv",
    )
