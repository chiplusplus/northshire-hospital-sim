import numpy as np
import pandas as pd


def random_dates(start, end, size, rng: np.random.Generator):
    """
    Generate random dates between start and end (inclusive of start, exclusive of end).
    start, end: strings or Timestamps ('2020-01-01')
    """
    start = np.datetime64(start, 'D')
    end = np.datetime64(end, 'D')
    start_int = start.astype('int64')
    end_int = end.astype('int64')
    # rng.randint returns int64 but we're turning them straight into datetime
    random_ints = rng.integers(start_int, end_int, size=size)
    return pd.to_datetime(random_ints, unit='D')

SPECIALTIES = [
    "cardiology", "respiratory", "endocrinology", "oncology", "orthopaedics",
    "dermatology", "gastroenterology", "neurology", "mental_health"
]

REFERRAL_REASONS = [
    "chest_pain", "breathlessness", "diabetes_review", "suspected_cancer",
    "mobility_issue", "skin_lesion", "abdominal_pain", "headache", "anxiety"
]

REFERRAL_PRIORITIES = ["routine", "urgent", "two_week_wait"]
SOURCE_TYPES = ["GP", "A&E", "Community", "Self"]
OUTCOMES = ["seen", "cancelled_by_patient", "cancelled_by_provider",
            "did_not_attend", "rejected"]

def generate_referrals(patients_df, providers_df, analysis_start, analysis_end, seed):
    rng = np.random.default_rng(seed)

    # Only use non-GP providers as targets
    acute_sites = providers_df[providers_df["provider_type"].isin(["ACUTE_HOSPITAL", "COMMUNITY_CLINIC", "DIAGNOSTIC_CENTRE", "URGENT_CARE"])]

    referral_rows = []

    for _, p in patients_df.iterrows():
        # base referrals per patient
        base = 0.2  # most people will have 0–1
        chronic_boost = min(p.get("chronic_conditions_count", 0) * 0.4, 2.0)
        deprivation_boost = 0.3 if p.get("imd_decile", 5) <= 3 else 0.0

        expected_referrals = base + chronic_boost + deprivation_boost
        # Poisson-ish draw
        n_referrals = rng.poisson(expected_referrals)
        if n_referrals == 0:
            continue

        # patient-specific date range – between reg_start and reg_end (or analysis window)
        reg_start = pd.to_datetime(p.get("registration_start_date", analysis_start))
        reg_end_raw = p.get("registration_end_date", None)
        reg_end = pd.to_datetime(reg_end_raw) if pd.notnull(reg_end_raw) else pd.to_datetime(analysis_end)

        start = max(reg_start, pd.to_datetime(analysis_start))
        end = min(reg_end, pd.to_datetime(analysis_end))

        if start >= end:
            continue

        referral_dates = random_dates(start, end, n_referrals, rng)

        for rd in referral_dates:
            source_type = rng.choice(SOURCE_TYPES, p=[0.7, 0.15, 0.1, 0.05])
            priority = rng.choice(REFERRAL_PRIORITIES, p=[0.75, 0.2, 0.05])

            # waiting time distribution – longer for routine, shorter for urgent
            if priority == "routine":
                wait_days = rng.integers(14, 120)
            elif priority == "urgent":
                wait_days = rng.integers(3, 21)
            else:  # two_week_wait
                wait_days = rng.integers(7, 21)

            first_appt_date = rd + pd.Timedelta(days=int(wait_days))

            specialty = rng.choice(SPECIALTIES)
            reason = rng.choice(REFERRAL_REASONS)

            # slightly worse delays for higher deprivation
            imd = p.get("imd_decile", 5)
            if imd <= 3 and rng.random() < 0.3:
                extra_delay = rng.integers(7, 60)
                first_appt_date += pd.Timedelta(days=int(extra_delay))

            outcome = rng.choice(OUTCOMES, p=[0.7, 0.05, 0.05, 0.15, 0.05])

            target_provider = acute_sites.sample(1).iloc[0]

            referral_rows.append({
                "patient_id": p["patient_id"],
                "source_type": source_type,
                "source_org_id": p.get("registered_gp_practice_id", None),
                "target_provider_id": target_provider["provider_id"],
                "referral_specialty": specialty,
                "referral_reason_code": reason,
                "referral_priority": priority,
                "referral_date": rd,
                "first_appointment_date": first_appt_date,
                "referral_outcome": outcome
            })

    referrals_df = pd.DataFrame(referral_rows)
    referrals_df.insert(0, "referral_id", range(1, len(referrals_df) + 1))
    return referrals_df

# Example usage
# referrals_df = generate_referrals(patients_df, providers_df)
# referrals_df.head()
