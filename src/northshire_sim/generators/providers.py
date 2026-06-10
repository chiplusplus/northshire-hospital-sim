"""
Provider/site generator.

Creates a synthetic provider dimension dataset (sites and services).
Returns a pandas DataFrame. All names and geography sourced from
the shared GM reference module (no Faker dependency).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from northshire_sim.generators.gm_reference import (
    GM_COMMUNITY_CLINIC_NAMES,
    GM_DIAGNOSTIC_CENTRE_NAMES,
    GM_GP_PRACTICE_NAMES,
    GM_HOSPITAL_NAMES,
    GM_LSOA_IMD_LOOKUP,
    GM_URGENT_CARE_NAMES,
    ICS_REGION,
    TRUST_NAME,
)

# Postcode prefix -> city name mapping for GM areas
_POSTCODE_CITY: dict[str, str] = {
    "M": "Manchester",
    "OL": "Oldham",
    "BL": "Bolton",
    "SK": "Stockport",
    "WN": "Wigan",
    "WA": "Warrington",
}


def _city_from_postcode(postcode_sector: str) -> str:
    """Derive city name from GM postcode sector prefix."""
    prefix = postcode_sector.split()[0]  # e.g. "M7" -> "M7"
    # Try 2-letter prefix first (OL, BL, SK, WN, WA), then 1-letter (M)
    for length in (2, 1):
        key = prefix[:length]
        if key in _POSTCODE_CITY:
            return _POSTCODE_CITY[key]
    return "Manchester"  # fallback


def _expand_postcode_sector(postcode_sector: str, rng: np.random.Generator) -> str:
    """Expand a postcode sector (e.g. 'M7 3') to a full postcode (e.g. 'M7 3AB')."""
    digit = rng.integers(0, 10)
    letter = chr(ord("A") + int(rng.integers(0, 26)))
    return f"{postcode_sector}{digit}{letter}"


def generate_providers(n_providers: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)

    n_hospitals = int(n_providers * 0.08)
    n_gp = int(n_providers * 0.60)
    n_community = int(n_providers * 0.16)
    n_urgent_care = int(n_providers * 0.08)
    n_diagnostic = int(n_providers * 0.08)

    records: list[dict] = []
    provider_id = 1

    def _pick_name(name_list: list[str], index: int) -> str:
        """Cycle through name list if batch size exceeds list length."""
        return name_list[index % len(name_list)]

    def add_provider_batch(count: int, ptype: str, name_list: list[str]) -> None:
        nonlocal provider_id
        for i in range(count):
            is_active = bool(rng.choice([True, False], p=[0.9, 0.1]))

            # Pick LSOA entry from GM reference
            lsoa_entry = GM_LSOA_IMD_LOOKUP[int(rng.integers(0, len(GM_LSOA_IMD_LOOKUP)))]
            postcode_sector = str(lsoa_entry["postcode_sector"])
            lsoa_code = str(lsoa_entry["lsoa_code"])
            postcode = _expand_postcode_sector(postcode_sector, rng)
            city = _city_from_postcode(postcode_sector)

            # Generate address from GM area
            street_num = int(rng.integers(1, 200))
            address_line_1 = f"{street_num} {city} Road"

            record = {
                "provider_id": provider_id,
                "provider_code": f"{ptype[:3].upper()}{provider_id:03d}",
                "provider_name": _pick_name(name_list, i),
                "provider_type": ptype,
                "parent_trust_name": TRUST_NAME,
                "ics_region": ICS_REGION,
                "address_line_1": address_line_1,
                "city": city,
                "postcode": postcode,
                "postcode_sector": postcode_sector,
                "lsoa_code": lsoa_code,
                "is_active": is_active,
            }
            records.append(record)
            provider_id += 1

    add_provider_batch(n_hospitals, "ACUTE_HOSPITAL", GM_HOSPITAL_NAMES)
    add_provider_batch(n_gp, "GP_PRACTICE", GM_GP_PRACTICE_NAMES)
    add_provider_batch(n_community, "COMMUNITY_CLINIC", GM_COMMUNITY_CLINIC_NAMES)
    add_provider_batch(n_urgent_care, "URGENT_CARE", GM_URGENT_CARE_NAMES)
    add_provider_batch(n_diagnostic, "DIAGNOSTIC_CENTRE", GM_DIAGNOSTIC_CENTRE_NAMES)

    return pd.DataFrame(records)
