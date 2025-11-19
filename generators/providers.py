import numpy as np
import pandas as pd
from faker import Faker
from datetime import date

fake = Faker("en_GB")

def generate_providers(
    n_providers,
    seed
):
    n_gp = int(n_providers * 0.6)
    n_hospitals = int(n_providers * 0.08)
    n_community = int(n_providers * 0.16)
    n_urgent_care = int(n_providers * 0.08)
    n_diagnostic = int(n_providers * 0.08)

    rng = np.random.default_rng(seed)

    records = []
    provider_id = 1


    # helper to derive sector from full postcode
    def get_postcode_sector(full_postcode: str) -> str:
        parts = full_postcode.split()
        return parts[0] if len(parts) >= 1 else full_postcode

    def add_provider_batch(count, ptype, name_template):
        nonlocal provider_id
        for i in range(count):
            is_active = bool(rng.choice([True, False], p=[0.9, 0.1]))

            postcode = fake.postcode()
            postcode_sector = get_postcode_sector(postcode)

            record = {
                "provider_id": provider_id,
                "provider_code": f"{ptype[:3].upper()}{provider_id:03d}",
                "provider_name": name_template.format(i + 1),
                "provider_type": ptype,
                "parent_trust_name": f"{fake.city()} Integrated Care Trust",
                "ics_region": f"{fake.city()} ICS",
                "address_line_1": fake.street_address(),
                "city": fake.city(),
                "postcode": postcode,
                "postcode_sector": postcode_sector,
                "lsoa_code": f"E010{rng.integers(10000, 99999)}",
                "is_active": is_active,
            }
            records.append(record)
            provider_id += 1

    add_provider_batch(n_hospitals, "ACUTE_HOSPITAL", "Northshire General Hospital {}")
    add_provider_batch(n_gp, "GP_PRACTICE", "Northshire GP Practice {}")
    add_provider_batch(n_community, "COMMUNITY_CLINIC", "Northshire Community Clinic {}")
    add_provider_batch(n_urgent_care, "URGENT_CARE", "Northshire Urgent Care Centre {}")
    add_provider_batch(n_diagnostic, "DIAGNOSTIC_CENTRE", "Northshire Diagnostics Hub {}")

    providers_df = pd.DataFrame(records)
    return providers_df
