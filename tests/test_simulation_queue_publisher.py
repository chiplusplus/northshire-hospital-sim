from datetime import date
from unittest.mock import MagicMock

import pandas as pd

from northshire_sim.publishing.simulation_queue import publish_simulation_queue


def test_uploads_each_day_folder():
    queue = {
        date(2026, 6, 2): {
            "appointments.csv": pd.DataFrame({"col": [1]}),
            "encounters.csv": pd.DataFrame({"col": [2]}),
        },
        date(2026, 6, 3): {
            "urgent_care_logs.csv": pd.DataFrame({"col": [3]}),
        },
    }

    s3 = MagicMock()

    count = publish_simulation_queue(s3=s3, bucket="trust-bucket", queue=queue)

    assert count == 3
    put_calls = s3.put_object.call_args_list
    keys = [c.kwargs["Key"] for c in put_calls]

    assert "_simulation_queue/day=2026-06-02/appointments.csv" in keys
    assert "_simulation_queue/day=2026-06-02/encounters.csv" in keys
    assert "_simulation_queue/day=2026-06-03/urgent_care_logs.csv" in keys


def test_empty_queue_no_uploads():
    s3 = MagicMock()
    count = publish_simulation_queue(s3=s3, bucket="trust-bucket", queue={})
    assert count == 0
    s3.put_object.assert_not_called()
