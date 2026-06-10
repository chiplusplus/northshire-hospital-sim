"""
Greater Manchester reference data module.

SYNTHETIC DATA — NOT REAL PATIENTS.

Single source of truth for all GM-specific constants used across generators:
demographics, geography, provider names, and scale defaults. Every generator
imports from this module — no hardcoded distributions scattered across files.

Sources:
  - ONS Census 2021 for Greater Manchester (ethnicity)
  - MHCLG Index of Deprivation 2019 (IMD deciles)
  - NHS Data Dictionary (ODS code format)
  - GM population pyramid (age bands)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Scale defaults (D-19)
# ---------------------------------------------------------------------------
DEFAULT_N_PATIENTS: int = 10_000
DEFAULT_N_PROVIDERS: int = 50

# ---------------------------------------------------------------------------
# Trust & ICS identity (D-24, D-25)
# ---------------------------------------------------------------------------
TRUST_NAME: str = "Northshire Integrated Care NHS Foundation Trust"
ICS_REGION: str = "Greater Manchester Integrated Care System"

# ---------------------------------------------------------------------------
# Age bands — includes 0-15 paediatric (D-21)
# ---------------------------------------------------------------------------
AGE_BAND_LABELS: list[str] = ["0-15", "16-24", "25-44", "45-64", "65-79", "80+"]
AGE_BAND_PROBS: list[float] = [0.18, 0.10, 0.28, 0.25, 0.14, 0.05]
AGE_BAND_RANGES: dict[str, tuple[int, int]] = {
    "0-15": (0, 15),
    "16-24": (16, 24),
    "25-44": (25, 44),
    "45-64": (45, 64),
    "65-79": (65, 79),
    "80+": (80, 95),
}

# ---------------------------------------------------------------------------
# Ethnicity — ONS 2021 Census for Greater Manchester (D-20)
#
# Totals: ~76.5% White, ~13.5% Asian, ~4.7% Black,
#         ~2.5% Mixed, ~2.2% Other, ~0.6% not stated
# ---------------------------------------------------------------------------
GM_ETHNICITY_CATEGORIES: list[str | None] = [
    "White British",
    "White Irish",
    "White Other",
    "Pakistani",
    "Bangladeshi",
    "Indian",
    "Chinese",
    "Other Asian",
    "Black African",
    "Black Caribbean",
    "Other Black",
    "White and Black Caribbean",
    "White and Asian",
    "Other Mixed",
    "Arab",
    "Any Other",
    None,  # "not stated" — NHS operational rate
]

GM_ETHNICITY_PROBS: list[float] = [
    0.680, 0.020, 0.065,                          # ~76.5% White
    0.065, 0.020, 0.025, 0.015, 0.010,            # ~13.5% Asian
    0.025, 0.012, 0.010,                           # ~4.7% Black
    0.010, 0.008, 0.007,                           # ~2.5% Mixed
    0.007, 0.015,                                  # ~2.2% Other
    0.006,                                         # ~0.6% not stated
]

# ---------------------------------------------------------------------------
# Clinician ethnicity — NHS workforce skew (D-27)
#
# Higher Asian/Other vs population (international recruitment patterns).
# Totals: ~65.5% White, ~19% Asian, ~4% Black,
#         ~2.5% Mixed, ~5% Other, ~4% not stated
# ---------------------------------------------------------------------------
GM_CLINICIAN_ETHNICITY_CATEGORIES: list[str | None] = GM_ETHNICITY_CATEGORIES

GM_CLINICIAN_ETHNICITY_PROBS: list[float] = [
    0.580, 0.020, 0.055,                          # ~65.5% White
    0.080, 0.030, 0.045, 0.020, 0.015,            # ~19% Asian
    0.020, 0.012, 0.008,                           # ~4% Black
    0.010, 0.008, 0.007,                           # ~2.5% Mixed
    0.010, 0.040,                                  # ~5% Other
    0.040,                                         # ~4% not stated
]

# ---------------------------------------------------------------------------
# Ethnicity groups with known wait-time disparity (for encounters.py)
# All non-White ONS categories that show inequality in NHS data.
# ---------------------------------------------------------------------------
ETHNICITY_GROUPS_WITH_DISPARITY: set[str] = {
    "Pakistani", "Bangladeshi", "Indian", "Chinese", "Other Asian",
    "Black African", "Black Caribbean", "Other Black",
    "White and Black Caribbean", "White and Asian", "Other Mixed",
    "Arab", "Any Other",
}

# ---------------------------------------------------------------------------
# Ethnicity-IMD correlation weights (for patients.py)
#
# Reflects real GM patterns: South Asian and Black communities are
# disproportionately concentrated in deprived LSOAs. The bias value
# controls how strongly each group's LSOA selection skews toward
# IMD deciles 1-3. 0.0 = population-average, 1.0 = maximum skew.
# ---------------------------------------------------------------------------
ETHNICITY_IMD_BIAS: dict[str, float] = {
    "Pakistani": 0.70,
    "Bangladeshi": 0.75,
    "Black African": 0.50,
    "Black Caribbean": 0.45,
    "Other Black": 0.40,
    "Indian": 0.20,
    "Arab": 0.45,
    "Other Asian": 0.25,
    "White and Black Caribbean": 0.30,
    "Other Mixed": 0.15,
}

# ---------------------------------------------------------------------------
# Geography — GM LSOAs with IMD deciles from MHCLG IoD 2019 (D-05, D-07)
#
# GM LSOAs span E01004768 (Bolton) to E01006489 (Wigan) across all 10 boroughs.
# Postcode sectors match the LSOA's actual GM area.
#
# Borough approximate ranges:
#   Bolton:     E01004768-E01004943   BL prefix
#   Bury:       E01004944-E01005065   BL/M prefix
#   Manchester: E01005066-E01005347   M prefix
#   Oldham:     E01005348-E01005503   OL prefix
#   Rochdale:   E01005504-E01005649   OL prefix
#   Salford:    E01005650-E01005829   M prefix
#   Stockport:  E01005830-E01006013   SK prefix
#   Tameside:   E01006014-E01006153   OL/SK prefix
#   Trafford:   E01006154-E01006289   M/WA prefix
#   Wigan:      E01006290-E01006489   WN/WA prefix
# ---------------------------------------------------------------------------
GM_LSOA_IMD_LOOKUP: list[dict[str, object]] = [
    # --- Decile 1 (most deprived) — Salford, Oldham, Rochdale, Bolton, Manchester ---
    {"lsoa_code": "E01005650", "imd_decile": 1, "postcode_sector": "M7 3"},     # Salford
    {"lsoa_code": "E01005655", "imd_decile": 1, "postcode_sector": "M7 1"},     # Salford
    {"lsoa_code": "E01005400", "imd_decile": 1, "postcode_sector": "OL1 2"},    # Oldham
    {"lsoa_code": "E01005410", "imd_decile": 1, "postcode_sector": "OL8 1"},    # Oldham
    {"lsoa_code": "E01004850", "imd_decile": 1, "postcode_sector": "BL3 6"},    # Bolton
    {"lsoa_code": "E01004860", "imd_decile": 1, "postcode_sector": "BL3 5"},    # Bolton
    {"lsoa_code": "E01005510", "imd_decile": 1, "postcode_sector": "OL11 1"},   # Rochdale
    {"lsoa_code": "E01005520", "imd_decile": 1, "postcode_sector": "OL16 2"},   # Rochdale
    {"lsoa_code": "E01005100", "imd_decile": 1, "postcode_sector": "M14 4"},    # Manchester
    {"lsoa_code": "E01005110", "imd_decile": 1, "postcode_sector": "M11 3"},    # Manchester

    # --- Decile 2 — Bolton, Manchester, Tameside, Wigan ---
    {"lsoa_code": "E01004870", "imd_decile": 2, "postcode_sector": "BL1 3"},    # Bolton
    {"lsoa_code": "E01004880", "imd_decile": 2, "postcode_sector": "BL2 1"},    # Bolton
    {"lsoa_code": "E01005120", "imd_decile": 2, "postcode_sector": "M40 7"},    # Manchester
    {"lsoa_code": "E01005130", "imd_decile": 2, "postcode_sector": "M9 4"},     # Manchester
    {"lsoa_code": "E01006020", "imd_decile": 2, "postcode_sector": "OL6 6"},    # Tameside
    {"lsoa_code": "E01006030", "imd_decile": 2, "postcode_sector": "OL7 0"},    # Tameside
    {"lsoa_code": "E01006300", "imd_decile": 2, "postcode_sector": "WN1 3"},    # Wigan
    {"lsoa_code": "E01006310", "imd_decile": 2, "postcode_sector": "WN5 0"},    # Wigan

    # --- Decile 3 — Bury, Rochdale, Salford, Manchester ---
    {"lsoa_code": "E01004950", "imd_decile": 3, "postcode_sector": "BL9 0"},    # Bury
    {"lsoa_code": "E01004960", "imd_decile": 3, "postcode_sector": "BL8 1"},    # Bury
    {"lsoa_code": "E01005530", "imd_decile": 3, "postcode_sector": "OL12 6"},   # Rochdale
    {"lsoa_code": "E01005540", "imd_decile": 3, "postcode_sector": "OL12 0"},   # Rochdale
    {"lsoa_code": "E01005660", "imd_decile": 3, "postcode_sector": "M6 5"},     # Salford
    {"lsoa_code": "E01005670", "imd_decile": 3, "postcode_sector": "M6 7"},     # Salford
    {"lsoa_code": "E01005140", "imd_decile": 3, "postcode_sector": "M8 5"},     # Manchester
    {"lsoa_code": "E01005150", "imd_decile": 3, "postcode_sector": "M18 7"},    # Manchester

    # --- Decile 4 — Wigan, Tameside, Oldham, Bolton ---
    {"lsoa_code": "E01006320", "imd_decile": 4, "postcode_sector": "WN2 3"},    # Wigan
    {"lsoa_code": "E01006330", "imd_decile": 4, "postcode_sector": "WN3 4"},    # Wigan
    {"lsoa_code": "E01006040", "imd_decile": 4, "postcode_sector": "SK14 1"},   # Tameside
    {"lsoa_code": "E01006050", "imd_decile": 4, "postcode_sector": "SK14 4"},   # Tameside
    {"lsoa_code": "E01005420", "imd_decile": 4, "postcode_sector": "OL4 1"},    # Oldham
    {"lsoa_code": "E01005430", "imd_decile": 4, "postcode_sector": "OL4 3"},    # Oldham
    {"lsoa_code": "E01004890", "imd_decile": 4, "postcode_sector": "BL4 7"},    # Bolton
    {"lsoa_code": "E01004900", "imd_decile": 4, "postcode_sector": "BL5 1"},    # Bolton

    # --- Decile 5 — Manchester, Salford, Bury, Rochdale ---
    {"lsoa_code": "E01005160", "imd_decile": 5, "postcode_sector": "M19 2"},    # Manchester
    {"lsoa_code": "E01005170", "imd_decile": 5, "postcode_sector": "M20 1"},    # Manchester
    {"lsoa_code": "E01005680", "imd_decile": 5, "postcode_sector": "M5 3"},     # Salford
    {"lsoa_code": "E01005690", "imd_decile": 5, "postcode_sector": "M50 1"},    # Salford
    {"lsoa_code": "E01004970", "imd_decile": 5, "postcode_sector": "BL0 9"},    # Bury
    {"lsoa_code": "E01004980", "imd_decile": 5, "postcode_sector": "M25 1"},    # Bury
    {"lsoa_code": "E01005550", "imd_decile": 5, "postcode_sector": "OL10 4"},   # Rochdale
    {"lsoa_code": "E01005560", "imd_decile": 5, "postcode_sector": "OL15 8"},   # Rochdale

    # --- Decile 6 — Stockport, Trafford, Wigan, Tameside ---
    {"lsoa_code": "E01005840", "imd_decile": 6, "postcode_sector": "SK1 3"},    # Stockport
    {"lsoa_code": "E01005850", "imd_decile": 6, "postcode_sector": "SK2 5"},    # Stockport
    {"lsoa_code": "E01006160", "imd_decile": 6, "postcode_sector": "M32 0"},    # Trafford
    {"lsoa_code": "E01006170", "imd_decile": 6, "postcode_sector": "M33 2"},    # Trafford
    {"lsoa_code": "E01006340", "imd_decile": 6, "postcode_sector": "WN4 8"},    # Wigan
    {"lsoa_code": "E01006350", "imd_decile": 6, "postcode_sector": "WN6 7"},    # Wigan
    {"lsoa_code": "E01006060", "imd_decile": 6, "postcode_sector": "SK15 1"},   # Tameside
    {"lsoa_code": "E01006070", "imd_decile": 6, "postcode_sector": "SK15 3"},   # Tameside

    # --- Decile 7 — Bury, Bolton, Stockport, Manchester ---
    {"lsoa_code": "E01004990", "imd_decile": 7, "postcode_sector": "BL9 5"},    # Bury
    {"lsoa_code": "E01005000", "imd_decile": 7, "postcode_sector": "BL9 7"},    # Bury
    {"lsoa_code": "E01004910", "imd_decile": 7, "postcode_sector": "BL6 4"},    # Bolton
    {"lsoa_code": "E01004920", "imd_decile": 7, "postcode_sector": "BL7 9"},    # Bolton
    {"lsoa_code": "E01005860", "imd_decile": 7, "postcode_sector": "SK3 8"},    # Stockport
    {"lsoa_code": "E01005870", "imd_decile": 7, "postcode_sector": "SK4 1"},    # Stockport
    {"lsoa_code": "E01005180", "imd_decile": 7, "postcode_sector": "M21 7"},    # Manchester
    {"lsoa_code": "E01005190", "imd_decile": 7, "postcode_sector": "M22 4"},    # Manchester

    # --- Decile 8 — Trafford, Stockport, Oldham, Salford ---
    {"lsoa_code": "E01006180", "imd_decile": 8, "postcode_sector": "M33 4"},    # Trafford
    {"lsoa_code": "E01006190", "imd_decile": 8, "postcode_sector": "WA15 6"},   # Trafford
    {"lsoa_code": "E01005880", "imd_decile": 8, "postcode_sector": "SK4 4"},    # Stockport
    {"lsoa_code": "E01005890", "imd_decile": 8, "postcode_sector": "SK5 6"},    # Stockport
    {"lsoa_code": "E01005440", "imd_decile": 8, "postcode_sector": "OL2 5"},    # Oldham
    {"lsoa_code": "E01005450", "imd_decile": 8, "postcode_sector": "OL3 5"},    # Oldham
    {"lsoa_code": "E01005700", "imd_decile": 8, "postcode_sector": "M27 4"},    # Salford
    {"lsoa_code": "E01005710", "imd_decile": 8, "postcode_sector": "M28 3"},    # Salford

    # --- Decile 9 — Stockport, Trafford, Bury, Manchester ---
    {"lsoa_code": "E01005900", "imd_decile": 9, "postcode_sector": "SK7 4"},    # Stockport
    {"lsoa_code": "E01005910", "imd_decile": 9, "postcode_sector": "SK8 1"},    # Stockport
    {"lsoa_code": "E01006200", "imd_decile": 9, "postcode_sector": "WA14 3"},   # Trafford
    {"lsoa_code": "E01006210", "imd_decile": 9, "postcode_sector": "WA14 5"},   # Trafford
    {"lsoa_code": "E01005010", "imd_decile": 9, "postcode_sector": "BL0 0"},    # Bury
    {"lsoa_code": "E01005020", "imd_decile": 9, "postcode_sector": "M45 6"},    # Bury
    {"lsoa_code": "E01005200", "imd_decile": 9, "postcode_sector": "M20 2"},    # Manchester
    {"lsoa_code": "E01005210", "imd_decile": 9, "postcode_sector": "M20 6"},    # Manchester

    # --- Decile 10 (least deprived) — Trafford, Stockport, Bolton, Bury ---
    {"lsoa_code": "E01006220", "imd_decile": 10, "postcode_sector": "WA15 0"},  # Trafford
    {"lsoa_code": "E01006230", "imd_decile": 10, "postcode_sector": "WA14 4"},  # Trafford
    {"lsoa_code": "E01005920", "imd_decile": 10, "postcode_sector": "SK7 1"},   # Stockport
    {"lsoa_code": "E01005930", "imd_decile": 10, "postcode_sector": "SK8 6"},   # Stockport
    {"lsoa_code": "E01004930", "imd_decile": 10, "postcode_sector": "BL1 7"},   # Bolton
    {"lsoa_code": "E01004940", "imd_decile": 10, "postcode_sector": "BL7 8"},   # Bolton
    {"lsoa_code": "E01005030", "imd_decile": 10, "postcode_sector": "BL8 4"},   # Bury
    {"lsoa_code": "E01005040", "imd_decile": 10, "postcode_sector": "M45 7"},   # Bury
]

# Postcode sectors derived from the LSOA lookup (for convenience)
GM_POSTCODE_SECTORS: list[str] = sorted(
    {e["postcode_sector"] for e in GM_LSOA_IMD_LOOKUP}
)

# ---------------------------------------------------------------------------
# GP Practices — synthetic P-prefixed ODS-style codes (D-08)
# Names themed on GM areas. Format: P + 5 digits (NHS ODS convention).
# ---------------------------------------------------------------------------
GM_GP_PRACTICES: list[dict[str, str]] = [
    {"practice_id": "P84001", "name": "Broughton Health Centre", "postcode_sector": "M7 1"},
    {"practice_id": "P84002", "name": "Levenshulme Medical Practice", "postcode_sector": "M19 2"},
    {"practice_id": "P84003", "name": "Salford Quays Surgery", "postcode_sector": "M50 1"},
    {"practice_id": "P84004", "name": "Cheetham Hill Medical Centre", "postcode_sector": "M8 5"},
    {"practice_id": "P84005", "name": "Rusholme Family Practice", "postcode_sector": "M14 4"},
    {"practice_id": "P84006", "name": "Gorton Medical Practice", "postcode_sector": "M18 7"},
    {"practice_id": "P84007", "name": "Whalley Range Surgery", "postcode_sector": "M21 7"},
    {"practice_id": "P84008", "name": "Didsbury Village Practice", "postcode_sector": "M20 2"},
    {"practice_id": "P84009", "name": "Withington Health Centre", "postcode_sector": "M20 1"},
    {"practice_id": "P84010", "name": "Wythenshawe Medical Practice", "postcode_sector": "M22 4"},
    {"practice_id": "P84011", "name": "Bolton Central Surgery", "postcode_sector": "BL1 3"},
    {"practice_id": "P84012", "name": "Farnworth Family Practice", "postcode_sector": "BL4 7"},
    {"practice_id": "P84013", "name": "Horwich Health Centre", "postcode_sector": "BL6 4"},
    {"practice_id": "P84014", "name": "Westhoughton Medical Centre", "postcode_sector": "BL5 1"},
    {"practice_id": "P84015", "name": "Bury Central Surgery", "postcode_sector": "BL9 0"},
    {"practice_id": "P84016", "name": "Ramsbottom Health Centre", "postcode_sector": "BL0 9"},
    {"practice_id": "P84017", "name": "Prestwich Medical Practice", "postcode_sector": "M25 1"},
    {"practice_id": "P84018", "name": "Whitefield Family Surgery", "postcode_sector": "M45 6"},
    {"practice_id": "P84019", "name": "Oldham Town Practice", "postcode_sector": "OL1 2"},
    {"practice_id": "P84020", "name": "Chadderton Health Centre", "postcode_sector": "OL8 1"},
    {"practice_id": "P84021", "name": "Saddleworth Medical Practice", "postcode_sector": "OL3 5"},
    {"practice_id": "P84022", "name": "Shaw Family Surgery", "postcode_sector": "OL2 5"},
    {"practice_id": "P84023", "name": "Rochdale Central Practice", "postcode_sector": "OL11 1"},
    {"practice_id": "P84024", "name": "Heywood Medical Centre", "postcode_sector": "OL10 4"},
    {"practice_id": "P84025", "name": "Middleton Health Centre", "postcode_sector": "OL16 2"},
    {"practice_id": "P84026", "name": "Littleborough Surgery", "postcode_sector": "OL15 8"},
    {"practice_id": "P84027", "name": "Irlam Medical Practice", "postcode_sector": "M6 5"},
    {"practice_id": "P84028", "name": "Eccles Family Surgery", "postcode_sector": "M6 7"},
    {"practice_id": "P84029", "name": "Swinton Health Centre", "postcode_sector": "M27 4"},
    {"practice_id": "P84030", "name": "Walkden Medical Practice", "postcode_sector": "M28 3"},
    {"practice_id": "P84031", "name": "Stockport Central Surgery", "postcode_sector": "SK1 3"},
    {"practice_id": "P84032", "name": "Hazel Grove Practice", "postcode_sector": "SK7 4"},
    {"practice_id": "P84033", "name": "Bramhall Health Centre", "postcode_sector": "SK7 1"},
    {"practice_id": "P84034", "name": "Cheadle Hulme Medical Practice", "postcode_sector": "SK8 6"},
    {"practice_id": "P84035", "name": "Marple Family Surgery", "postcode_sector": "SK8 1"},
    {"practice_id": "P84036", "name": "Ashton Medical Centre", "postcode_sector": "OL6 6"},
    {"practice_id": "P84037", "name": "Denton Health Centre", "postcode_sector": "SK14 1"},
    {"practice_id": "P84038", "name": "Hyde Family Practice", "postcode_sector": "SK14 4"},
    {"practice_id": "P84039", "name": "Stalybridge Surgery", "postcode_sector": "SK15 1"},
    {"practice_id": "P84040", "name": "Sale Medical Practice", "postcode_sector": "M33 2"},
    {"practice_id": "P84041", "name": "Stretford Health Centre", "postcode_sector": "M32 0"},
    {"practice_id": "P84042", "name": "Altrincham Family Surgery", "postcode_sector": "WA14 3"},
    {"practice_id": "P84043", "name": "Urmston Medical Practice", "postcode_sector": "M33 4"},
    {"practice_id": "P84044", "name": "Hale Barns Health Centre", "postcode_sector": "WA15 0"},
    {"practice_id": "P84045", "name": "Wigan Central Surgery", "postcode_sector": "WN1 3"},
    {"practice_id": "P84046", "name": "Hindley Medical Practice", "postcode_sector": "WN2 3"},
    {"practice_id": "P84047", "name": "Leigh Health Centre", "postcode_sector": "WN4 8"},
    {"practice_id": "P84048", "name": "Standish Family Surgery", "postcode_sector": "WN6 7"},
    {"practice_id": "P84049", "name": "Atherton Medical Practice", "postcode_sector": "WN5 0"},
    {"practice_id": "P84050", "name": "Aspull Health Centre", "postcode_sector": "WN3 4"},
]

# ---------------------------------------------------------------------------
# Provider names — GM-themed synthetic names (D-24, D-25, D-26)
# ---------------------------------------------------------------------------
GM_HOSPITAL_NAMES: list[str] = [
    "Northshire Royal Infirmary",
    "Pennine General Hospital",
    "Oldham Community Hospital",
    "Salford Royal Hospital",
]

GM_GP_PRACTICE_NAMES: list[str] = [entry["name"] for entry in GM_GP_PRACTICES]

GM_COMMUNITY_CLINIC_NAMES: list[str] = [
    "Ashton Community Health Centre",
    "Bury Integrated Care Hub",
    "Eccles Community Clinic",
    "Gorton Neighbourhood Health Centre",
    "Heywood Community Practice",
    "Longsight Wellbeing Centre",
    "Middleton Community Hub",
    "Moss Side Health Centre",
]

GM_URGENT_CARE_NAMES: list[str] = [
    "Rochdale Urgent Care Centre",
    "Tameside Walk-in Centre",
    "Bolton Minor Injuries Unit",
    "Wigan Urgent Treatment Centre",
]

GM_DIAGNOSTIC_CENTRE_NAMES: list[str] = [
    "Wythenshawe Diagnostics Hub",
    "Trafford Imaging Centre",
    "Stockport Pathology Services",
    "Oldham Diagnostic Unit",
]

# ---------------------------------------------------------------------------
# Assertions — fail-fast if constants are inconsistent
# ---------------------------------------------------------------------------
assert len(GM_ETHNICITY_CATEGORIES) == len(GM_ETHNICITY_PROBS), (
    f"Ethnicity categories/probs length mismatch: "
    f"{len(GM_ETHNICITY_CATEGORIES)} != {len(GM_ETHNICITY_PROBS)}"
)
assert abs(sum(GM_ETHNICITY_PROBS) - 1.0) < 1e-9, (
    f"GM_ETHNICITY_PROBS sum = {sum(GM_ETHNICITY_PROBS)}, expected 1.0"
)
assert len(GM_CLINICIAN_ETHNICITY_CATEGORIES) == len(GM_CLINICIAN_ETHNICITY_PROBS), (
    f"Clinician ethnicity categories/probs length mismatch: "
    f"{len(GM_CLINICIAN_ETHNICITY_CATEGORIES)} != {len(GM_CLINICIAN_ETHNICITY_PROBS)}"
)
assert abs(sum(GM_CLINICIAN_ETHNICITY_PROBS) - 1.0) < 1e-9, (
    f"GM_CLINICIAN_ETHNICITY_PROBS sum = {sum(GM_CLINICIAN_ETHNICITY_PROBS)}, expected 1.0"
)
assert abs(sum(AGE_BAND_PROBS) - 1.0) < 1e-9, (
    f"AGE_BAND_PROBS sum = {sum(AGE_BAND_PROBS)}, expected 1.0"
)
assert len(AGE_BAND_LABELS) == len(AGE_BAND_PROBS), (
    f"Age band labels/probs length mismatch: "
    f"{len(AGE_BAND_LABELS)} != {len(AGE_BAND_PROBS)}"
)
