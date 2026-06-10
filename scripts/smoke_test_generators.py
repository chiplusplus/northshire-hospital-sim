from datetime import date
import pandas as pd

from src.northshire_sim.generators.patients import generate_patients
from src.northshire_sim.generators.providers import generate_providers
from src.northshire_sim.generators.clinicians import generate_clinicians
from src.northshire_sim.generators.encounters import generate_encounters
from src.northshire_sim.generators.referrals import generate_referrals
from src.northshire_sim.generators.diagnostics import generate_diagnostics
from src.northshire_sim.generators.urgent_care import generate_urgent_care_logs

SEED = 42

def main():
    # keep numbers small for speed
    n_patients = 10_000
    n_providers = 50

    patients = generate_patients(n_patients, seed=SEED)
    providers = generate_providers(n_providers, seed=SEED)
    clinicians = generate_clinicians(providers_df=providers, seed=SEED)

    encounters = generate_encounters(
        patients_df=patients,
        providers_df=providers,
        clinicians_df=clinicians,
        start_date=date(2023, 1, 1),
        end_date=date(2024, 12, 31),
        seed=SEED,
    )

    referrals = generate_referrals(encounters_df=encounters, providers_df=providers, seed=SEED)
    diagnostics = generate_diagnostics(referrals_df=referrals, patients_df=patients, encounters_df=encounters, seed=SEED)
    urgent_care = generate_urgent_care_logs(encounters_df=encounters, patients_df=patients, providers_df=providers, seed=SEED)

    print("patients:", patients.shape)
    print("providers:", providers.shape)
    print("clinicians:", clinicians.shape)
    print("encounters:", encounters.shape)
    print("referrals:", referrals.shape)
    print("diagnostics:", diagnostics.shape)
    print("urgent_care:", urgent_care.shape)

    # basic checks
    assert not patients.empty
    assert patients["patient_id"].is_unique
    assert providers["provider_id"].is_unique
    assert clinicians["clinician_id"].is_unique if not clinicians.empty else True
    assert encounters["encounter_id"].is_unique if not encounters.empty else True

    # FK checks
    assert set(encounters["patient_id"]).issubset(set(patients["patient_id"]))
    assert set(encounters["provider_id"]).issubset(set(providers["provider_id"]))
    if "clinician_id" in encounters.columns and not encounters["clinician_id"].isna().all():
        assert set(encounters["clinician_id"].dropna()).issubset(set(clinicians["clinician_id"]))

    print("✅ Smoke test passed")

if __name__ == "__main__":
    main()
