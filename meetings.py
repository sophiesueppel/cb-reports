# Central bank committee meeting dates and decisions, 2021–2026
# Sources: federalreserve.gov, ecb.europa.eu, bankofengland.co.uk
# Fed/BoE vote format: majority–minority. Arrow: ▼ cut, ▲ hike.
# ECB does not publish individual Governing Council votes.
# Note: 2025 H2 Fed/BoE/ECB decisions inferred from known 2026 starting rates.
#
# The lists below are the SEED / offline fallback. At runtime the live data lives
# in the SQLite `meetings` table (seeded from here, then refreshed from official
# sites — see meetings_store.py and meetings_extractor.py). Consumers should call
# get_meetings(bank) rather than reading a *_MEETINGS list directly.

import os

# ---------------------------------------------------------------------------
# FEDERAL RESERVE
# ---------------------------------------------------------------------------

FED_MEETINGS_2021 = [
    {"date": "2021-01-27", "decision": "hold", "rate": "0–0.25%",   "label": "Rates held · 11–0"},
    {"date": "2021-03-17", "decision": "hold", "rate": "0–0.25%",   "label": "Rates held · 11–0"},
    {"date": "2021-04-28", "decision": "hold", "rate": "0–0.25%",   "label": "Rates held · 11–0"},
    {"date": "2021-06-16", "decision": "hold", "rate": "0–0.25%",   "label": "Rates held · 11–0"},
    {"date": "2021-07-28", "decision": "hold", "rate": "0–0.25%",   "label": "Rates held · 11–0"},
    {"date": "2021-09-22", "decision": "hold", "rate": "0–0.25%",   "label": "Rates held · 11–0"},
    {"date": "2021-11-03", "decision": "hold", "rate": "0–0.25%",   "label": "Rates held · 11–0"},
    {"date": "2021-12-15", "decision": "hold", "rate": "0–0.25%",   "label": "Rates held · 11–0"},
]

FED_MEETINGS_2022 = [
    {"date": "2022-01-26", "decision": "hold", "rate": "0–0.25%",     "label": "Rates held · 11–0"},
    {"date": "2022-03-16", "decision": "hike", "rate": "0.25–0.50%",
     "note": "Unanimous 9–0. First hike since 2018.",
     "label": "+25bp hike"},
    {"date": "2022-05-04", "decision": "hike", "rate": "0.75–1.00%",
     "note": "Unanimous.",
     "label": "+50bp hike"},
    {"date": "2022-06-15", "decision": "hike", "rate": "1.50–1.75%",
     "note": "9–1. George dissented, preferred +50bp.",
     "label": "+75bp hike · 9–1"},
    {"date": "2022-07-27", "decision": "hike", "rate": "2.25–2.50%",
     "note": "Unanimous.",
     "label": "+75bp hike"},
    {"date": "2022-09-21", "decision": "hike", "rate": "3.00–3.25%",
     "note": "Unanimous.",
     "label": "+75bp hike"},
    {"date": "2022-11-02", "decision": "hike", "rate": "3.75–4.00%",
     "note": "Unanimous.",
     "label": "+75bp hike"},
    {"date": "2022-12-14", "decision": "hike", "rate": "4.25–4.50%",
     "note": "Unanimous.",
     "label": "+50bp hike"},
]

FED_MEETINGS_2023 = [
    {"date": "2023-02-01", "decision": "hike", "rate": "4.50–4.75%",
     "note": "Unanimous.",
     "label": "+25bp hike"},
    {"date": "2023-03-22", "decision": "hike", "rate": "4.75–5.00%",
     "note": "Unanimous.",
     "label": "+25bp hike"},
    {"date": "2023-05-03", "decision": "hike", "rate": "5.00–5.25%",
     "note": "Unanimous.",
     "label": "+25bp hike"},
    {"date": "2023-06-14", "decision": "hold", "rate": "5.00–5.25%",  "label": "Rates held · 11–0"},
    {"date": "2023-07-26", "decision": "hike", "rate": "5.25–5.50%",
     "note": "Unanimous.",
     "label": "+25bp hike"},
    {"date": "2023-09-20", "decision": "hold", "rate": "5.25–5.50%",  "label": "Rates held · 11–0"},
    {"date": "2023-11-01", "decision": "hold", "rate": "5.25–5.50%",  "label": "Rates held · 11–0"},
    {"date": "2023-12-13", "decision": "hold", "rate": "5.25–5.50%",  "label": "Rates held · 11–0"},
]

FED_MEETINGS_2024 = [
    {"date": "2024-01-31", "decision": "hold", "rate": "5.25–5.50%",  "label": "Rates held · 11–0"},
    {"date": "2024-03-20", "decision": "hold", "rate": "5.25–5.50%",  "label": "Rates held · 11–0"},
    {"date": "2024-05-01", "decision": "hold", "rate": "5.25–5.50%",  "label": "Rates held · 11–0"},
    {"date": "2024-06-12", "decision": "hold", "rate": "5.25–5.50%",  "label": "Rates held · 11–0"},
    {"date": "2024-07-31", "decision": "hold", "rate": "5.25–5.50%",  "label": "Rates held · 11–0"},
    {"date": "2024-09-18", "decision": "cut",  "rate": "4.75–5.00%",
     "note": "11–1. Bowman dissented, preferred −25bp.",
     "label": "−50bp cut · 11–1"},
    {"date": "2024-11-07", "decision": "cut",  "rate": "4.50–4.75%",
     "note": "Unanimous.",
     "label": "−25bp cut"},
    {"date": "2024-12-18", "decision": "cut",  "rate": "4.25–4.50%",
     "note": "11–1. Hamack dissented, preferred hold.",
     "label": "−25bp cut · 11–1"},
]

FED_MEETINGS_2025 = [
    {"date": "2025-01-29", "decision": "hold", "rate": "4.25–4.50%",  "label": "Rates held"},
    {"date": "2025-03-19", "decision": "hold", "rate": "4.25–4.50%",  "label": "Rates held"},
    {"date": "2025-05-07", "decision": "hold", "rate": "4.25–4.50%",  "label": "Rates held"},
    {"date": "2025-06-18", "decision": "hold", "rate": "4.25–4.50%",  "label": "Rates held"},
    {"date": "2025-07-30", "decision": "hold", "rate": "4.25–4.50%",  "label": "Rates held"},
    {"date": "2025-09-17", "decision": "cut",  "rate": "4.00–4.25%",  "label": "−25bp cut"},
    {"date": "2025-10-29", "decision": "cut",  "rate": "3.75–4.00%",  "label": "−25bp cut"},
    {"date": "2025-12-10", "decision": "cut",  "rate": "3.50–3.75%",  "label": "−25bp cut"},
]

FED_MEETINGS_2026 = [
    {"date": "2026-01-28", "decision": "hold", "rate": "3.50–3.75%",
     "note": "2 dissented, preferred −25bp cut",
     "label": "Rates held · 9–2 ▼"},
    {"date": "2026-03-18", "decision": "hold", "rate": "3.50–3.75%",
     "note": "1 dissent (Miran), preferred −25bp cut",
     "label": "Rates held · 10–1 ▼"},
    {"date": "2026-04-29", "decision": "hold", "rate": "3.50–3.75%",
     "note": "4 dissents: Miran (−25bp cut); Hammack/Kashkari/Logan (objected to easing bias in statement)",
     "label": "Rates held · 8–4"},
    {"date": "2026-06-17", "decision": "hold", "rate": "3.50–3.75%",
     "note": "Unanimous. First meeting chaired by Kevin Warsh.",
     "label": "Rates held · 12–0"},
    {"date": "2026-07-29", "decision": "upcoming", "label": "Jul 29"},
    {"date": "2026-09-16", "decision": "upcoming", "label": "Sep 16"},
    {"date": "2026-10-28", "decision": "upcoming", "label": "Oct 28"},
    {"date": "2026-12-09", "decision": "upcoming", "label": "Dec 9"},
]

FED_MEETINGS = (
    FED_MEETINGS_2021 + FED_MEETINGS_2022 + FED_MEETINGS_2023 +
    FED_MEETINGS_2024 + FED_MEETINGS_2025 + FED_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# EUROPEAN CENTRAL BANK
# ---------------------------------------------------------------------------

ECB_MEETINGS_2021 = [
    {"date": "2021-03-11", "decision": "hold", "rate": "−0.50%",  "label": "Rates held"},
    {"date": "2021-04-22", "decision": "hold", "rate": "−0.50%",  "label": "Rates held"},
    {"date": "2021-06-10", "decision": "hold", "rate": "−0.50%",  "label": "Rates held"},
    {"date": "2021-07-22", "decision": "hold", "rate": "−0.50%",  "label": "Rates held"},
    {"date": "2021-09-09", "decision": "hold", "rate": "−0.50%",  "label": "Rates held"},
    {"date": "2021-10-28", "decision": "hold", "rate": "−0.50%",  "label": "Rates held"},
    {"date": "2021-12-16", "decision": "hold", "rate": "−0.50%",  "label": "Rates held"},
]

ECB_MEETINGS_2022 = [
    {"date": "2022-02-03", "decision": "hold", "rate": "−0.50%",
     "note": "ECB does not publish individual votes.",
     "label": "Rates held"},
    {"date": "2022-03-10", "decision": "hold", "rate": "−0.50%",
     "note": "ECB does not publish individual votes.",
     "label": "Rates held"},
    {"date": "2022-04-14", "decision": "hold", "rate": "−0.50%",
     "note": "ECB does not publish individual votes.",
     "label": "Rates held"},
    {"date": "2022-06-09", "decision": "hold", "rate": "−0.50%",
     "note": "Pre-announced July hike.",
     "label": "Rates held"},
    {"date": "2022-07-21", "decision": "hike", "rate": "0.00%",
     "note": "First hike since 2011. ECB does not publish individual votes.",
     "label": "+50bp hike"},
    {"date": "2022-09-08", "decision": "hike", "rate": "0.75%",
     "note": "ECB does not publish individual votes.",
     "label": "+75bp hike"},
    {"date": "2022-10-27", "decision": "hike", "rate": "1.50%",
     "note": "ECB does not publish individual votes.",
     "label": "+75bp hike"},
    {"date": "2022-12-15", "decision": "hike", "rate": "2.00%",
     "note": "ECB does not publish individual votes.",
     "label": "+50bp hike"},
]

ECB_MEETINGS_2023 = [
    {"date": "2023-02-02", "decision": "hike", "rate": "2.50%",
     "note": "ECB does not publish individual votes.",
     "label": "+50bp hike"},
    {"date": "2023-03-16", "decision": "hike", "rate": "3.00%",
     "note": "ECB does not publish individual votes.",
     "label": "+50bp hike"},
    {"date": "2023-05-04", "decision": "hike", "rate": "3.25%",
     "note": "ECB does not publish individual votes.",
     "label": "+25bp hike"},
    {"date": "2023-06-15", "decision": "hike", "rate": "3.50%",
     "note": "ECB does not publish individual votes.",
     "label": "+25bp hike"},
    {"date": "2023-07-27", "decision": "hike", "rate": "3.75%",
     "note": "ECB does not publish individual votes.",
     "label": "+25bp hike"},
    {"date": "2023-09-14", "decision": "hike", "rate": "4.00%",
     "note": "ECB does not publish individual votes. Final hike of the cycle.",
     "label": "+25bp hike"},
    {"date": "2023-10-26", "decision": "hold", "rate": "4.00%",   "label": "Rates held"},
    {"date": "2023-12-14", "decision": "hold", "rate": "4.00%",   "label": "Rates held"},
]

ECB_MEETINGS_2024 = [
    {"date": "2024-01-25", "decision": "hold", "rate": "4.00%",   "label": "Rates held"},
    {"date": "2024-03-07", "decision": "hold", "rate": "4.00%",   "label": "Rates held"},
    {"date": "2024-04-11", "decision": "hold", "rate": "4.00%",   "label": "Rates held"},
    {"date": "2024-06-06", "decision": "cut",  "rate": "3.75%",
     "note": "First cut since 2019. ECB does not publish individual votes.",
     "label": "−25bp cut"},
    {"date": "2024-07-18", "decision": "hold", "rate": "3.75%",   "label": "Rates held"},
    {"date": "2024-09-12", "decision": "cut",  "rate": "3.50%",
     "note": "ECB does not publish individual votes.",
     "label": "−25bp cut"},
    {"date": "2024-10-17", "decision": "cut",  "rate": "3.25%",
     "note": "ECB does not publish individual votes.",
     "label": "−25bp cut"},
    {"date": "2024-12-12", "decision": "cut",  "rate": "3.00%",
     "note": "ECB does not publish individual votes.",
     "label": "−25bp cut"},
]

ECB_MEETINGS_2025 = [
    {"date": "2025-01-30", "decision": "cut",  "rate": "2.75%",
     "note": "ECB does not publish individual votes.",
     "label": "−25bp cut"},
    {"date": "2025-03-06", "decision": "cut",  "rate": "2.50%",
     "note": "ECB does not publish individual votes.",
     "label": "−25bp cut"},
    {"date": "2025-04-17", "decision": "cut",  "rate": "2.25%",
     "note": "ECB does not publish individual votes.",
     "label": "−25bp cut"},
    {"date": "2025-06-05", "decision": "cut",  "rate": "2.00%",
     "note": "ECB does not publish individual votes.",
     "label": "−25bp cut"},
    {"date": "2025-07-24", "decision": "hold", "rate": "2.00%",   "label": "Rates held"},
    {"date": "2025-09-11", "decision": "hold", "rate": "2.00%",   "label": "Rates held"},
    {"date": "2025-10-30", "decision": "hold", "rate": "2.00%",   "label": "Rates held"},
    {"date": "2025-12-18", "decision": "hold", "rate": "2.00%",   "label": "Rates held"},
]

ECB_MEETINGS_2026 = [
    {"date": "2026-03-19", "decision": "hold", "rate": "2.00%",
     "note": "ECB does not publish individual votes",
     "label": "Rates held"},
    {"date": "2026-04-30", "decision": "hold", "rate": "2.00%",
     "note": "ECB does not publish individual votes",
     "label": "Rates held"},
    {"date": "2026-06-11", "decision": "hike", "rate": "2.25%",
     "note": "Deposit facility raised +25bp to 2.25%. ECB does not publish individual votes.",
     "label": "+25bp hike"},
    {"date": "2026-07-23", "decision": "upcoming", "label": "Jul 23"},
    {"date": "2026-09-10", "decision": "upcoming", "label": "Sep 10"},
    {"date": "2026-10-29", "decision": "upcoming", "label": "Oct 29"},
    {"date": "2026-12-17", "decision": "upcoming", "label": "Dec 17"},
]

ECB_MEETINGS = (
    ECB_MEETINGS_2021 + ECB_MEETINGS_2022 + ECB_MEETINGS_2023 +
    ECB_MEETINGS_2024 + ECB_MEETINGS_2025 + ECB_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# BANK OF ENGLAND
# ---------------------------------------------------------------------------

BOE_MEETINGS_2021 = [
    {"date": "2021-02-04", "decision": "hold", "rate": "0.10%",
     "note": "Unanimous 9–0.",
     "label": "Rates held · 9–0"},
    {"date": "2021-03-18", "decision": "hold", "rate": "0.10%",
     "note": "Unanimous 9–0.",
     "label": "Rates held · 9–0"},
    {"date": "2021-05-06", "decision": "hold", "rate": "0.10%",
     "note": "Unanimous 9–0.",
     "label": "Rates held · 9–0"},
    {"date": "2021-06-24", "decision": "hold", "rate": "0.10%",
     "note": "Unanimous 9–0.",
     "label": "Rates held · 9–0"},
    {"date": "2021-08-05", "decision": "hold", "rate": "0.10%",
     "note": "7–2. Saunders & Ramsden voted to end QE early.",
     "label": "Rates held · 7–2"},
    {"date": "2021-09-23", "decision": "hold", "rate": "0.10%",
     "note": "7–2. Saunders & Ramsden voted to end QE early.",
     "label": "Rates held · 7–2"},
    {"date": "2021-11-04", "decision": "hold", "rate": "0.10%",
     "note": "7–2. Saunders preferred +15bp hike.",
     "label": "Rates held · 7–2 ▲"},
    {"date": "2021-12-16", "decision": "hike", "rate": "0.25%",
     "note": "Unanimous 9–0. First hike since August 2018.",
     "label": "+15bp hike · 9–0"},
]

BOE_MEETINGS_2022 = [
    {"date": "2022-02-03", "decision": "hike", "rate": "0.50%",
     "note": "5–4. Four members preferred a larger +50bp hike.",
     "label": "+25bp hike · 5–4 ▲"},
    {"date": "2022-03-17", "decision": "hike", "rate": "0.75%",
     "note": "8–1. Tenreyro voted to hold.",
     "label": "+25bp hike · 8–1"},
    {"date": "2022-05-05", "decision": "hike", "rate": "1.00%",
     "note": "6–3. Three members preferred a larger +50bp hike.",
     "label": "+25bp hike · 6–3 ▲"},
    {"date": "2022-06-16", "decision": "hike", "rate": "1.25%",
     "note": "6–3. Three members preferred +50bp.",
     "label": "+25bp hike · 6–3 ▲"},
    {"date": "2022-08-04", "decision": "hike", "rate": "1.75%",
     "note": "8–1. Tenreyro voted +25bp.",
     "label": "+50bp hike · 8–1"},
    {"date": "2022-09-22", "decision": "hike", "rate": "2.25%",
     "note": "5–4 split: 3 wanted +75bp, 1 wanted +25bp.",
     "label": "+50bp hike · 5–4"},
    {"date": "2022-11-03", "decision": "hike", "rate": "3.00%",
     "note": "7–2. Dhingra preferred +25bp; Tenreyro preferred +25bp.",
     "label": "+75bp hike · 7–2"},
    {"date": "2022-12-15", "decision": "hike", "rate": "3.50%",
     "note": "6–3. Two preferred +75bp; one preferred +25bp.",
     "label": "+50bp hike · 6–3"},
]

BOE_MEETINGS_2023 = [
    {"date": "2023-02-02", "decision": "hike", "rate": "4.00%",
     "note": "7–2. Tenreyro & Dhingra voted to hold.",
     "label": "+50bp hike · 7–2"},
    {"date": "2023-03-23", "decision": "hike", "rate": "4.25%",
     "note": "7–2. Tenreyro & Dhingra voted to hold.",
     "label": "+25bp hike · 7–2"},
    {"date": "2023-05-11", "decision": "hike", "rate": "4.50%",
     "note": "7–2. Tenreyro & Dhingra voted to hold.",
     "label": "+25bp hike · 7–2"},
    {"date": "2023-06-22", "decision": "hike", "rate": "5.00%",
     "note": "7–2. Two voted to hold.",
     "label": "+50bp hike · 7–2"},
    {"date": "2023-08-03", "decision": "hike", "rate": "5.25%",
     "note": "6–3. Three voted to hold.",
     "label": "+25bp hike · 6–3"},
    {"date": "2023-09-21", "decision": "hold", "rate": "5.25%",
     "note": "8–1. Haskel voted +25bp.",
     "label": "Rates held · 8–1 ▲"},
    {"date": "2023-11-02", "decision": "hold", "rate": "5.25%",
     "note": "6–3. Three voted +25bp hike.",
     "label": "Rates held · 6–3 ▲"},
    {"date": "2023-12-14", "decision": "hold", "rate": "5.25%",
     "note": "6–3. Three voted +25bp hike.",
     "label": "Rates held · 6–3 ▲"},
]

BOE_MEETINGS_2024 = [
    {"date": "2024-02-01", "decision": "hold", "rate": "5.25%",
     "note": "6–3. Two voted −25bp; one voted +25bp.",
     "label": "Rates held · 6–3"},
    {"date": "2024-03-21", "decision": "hold", "rate": "5.25%",
     "note": "8–1. Dhingra voted −25bp.",
     "label": "Rates held · 8–1 ▼"},
    {"date": "2024-05-09", "decision": "hold", "rate": "5.25%",
     "note": "7–2. Two voted −25bp.",
     "label": "Rates held · 7–2 ▼"},
    {"date": "2024-06-20", "decision": "hold", "rate": "5.25%",
     "note": "7–2. Two voted −25bp.",
     "label": "Rates held · 7–2 ▼"},
    {"date": "2024-08-01", "decision": "cut",  "rate": "5.00%",
     "note": "5–4. Very close vote.",
     "label": "−25bp cut · 5–4"},
    {"date": "2024-09-19", "decision": "hold", "rate": "5.00%",
     "note": "8–1. Dhingra voted −25bp.",
     "label": "Rates held · 8–1 ▼"},
    {"date": "2024-11-07", "decision": "cut",  "rate": "4.75%",
     "note": "8–1. Mann voted to hold.",
     "label": "−25bp cut · 8–1"},
    {"date": "2024-12-19", "decision": "hold", "rate": "4.75%",
     "note": "6–3. Three voted −25bp.",
     "label": "Rates held · 6–3 ▼"},
]

BOE_MEETINGS_2025 = [
    {"date": "2025-02-06", "decision": "cut",  "rate": "4.50%",
     "note": "Close vote.",
     "label": "−25bp cut"},
    {"date": "2025-03-20", "decision": "hold", "rate": "4.50%",   "label": "Rates held"},
    {"date": "2025-05-08", "decision": "cut",  "rate": "4.25%",   "label": "−25bp cut"},
    {"date": "2025-06-19", "decision": "hold", "rate": "4.25%",   "label": "Rates held"},
    {"date": "2025-08-07", "decision": "cut",  "rate": "4.00%",   "label": "−25bp cut"},
    {"date": "2025-09-18", "decision": "hold", "rate": "4.00%",   "label": "Rates held"},
    {"date": "2025-11-06", "decision": "cut",  "rate": "3.75%",   "label": "−25bp cut"},
    {"date": "2025-12-18", "decision": "hold", "rate": "3.75%",   "label": "Rates held"},
]

BOE_MEETINGS_2026 = [
    {"date": "2026-02-04", "decision": "hold", "rate": "3.75%",
     "note": "4 members voted to cut −25bp to 3.5%",
     "label": "Rates held · 5–4 ▼"},
    {"date": "2026-03-18", "decision": "hold", "rate": "3.75%",
     "note": "Unanimous",
     "label": "Rates held · 9–0"},
    {"date": "2026-04-29", "decision": "hold", "rate": "3.75%",
     "note": "1 member voted to hike +25bp to 4%",
     "label": "Rates held · 8–1 ▲"},
    {"date": "2026-06-17", "decision": "hold", "rate": "3.75%",
     "note": "2 members voted to hike +25bp to 4%",
     "label": "Rates held · 7–2 ▲"},
    {"date": "2026-07-30", "decision": "upcoming", "label": "Jul 30"},
    {"date": "2026-09-17", "decision": "upcoming", "label": "Sep 17"},
    {"date": "2026-11-05", "decision": "upcoming", "label": "Nov 5"},
    {"date": "2026-12-17", "decision": "upcoming", "label": "Dec 17"},
]

BOE_MEETINGS = (
    BOE_MEETINGS_2021 + BOE_MEETINGS_2022 + BOE_MEETINGS_2023 +
    BOE_MEETINGS_2024 + BOE_MEETINGS_2025 + BOE_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# BANK OF JAPAN
# ---------------------------------------------------------------------------
# Rate shown is the short-term policy interest rate target.
# Before March 2024: -0.10% (Negative Interest Rate Policy, NIRP).
# The BoJ does not publish individual vote counts.

BOJ_MEETINGS_2021 = [
    {"date": "2021-01-21", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2021-03-19", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2021-04-27", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2021-06-18", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2021-07-16", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2021-09-22", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2021-10-28", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2021-12-17", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
]

BOJ_MEETINGS_2022 = [
    {"date": "2022-01-18", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2022-03-18", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2022-04-28", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2022-06-17", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2022-07-21", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2022-09-22", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2022-10-28", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2022-12-20", "decision": "hold", "rate": "-0.10%",
     "note": "YCC band widened from ±0.25% to ±0.50%. Rate unchanged.",
     "label": "Rates held (YCC widened)"},
]

BOJ_MEETINGS_2023 = [
    {"date": "2023-01-18", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2023-03-10", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2023-04-28", "decision": "hold", "rate": "-0.10%",
     "note": "Governor Ueda's first meeting.",
     "label": "Rates held"},
    {"date": "2023-06-16", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2023-07-28", "decision": "hold", "rate": "-0.10%",
     "note": "YCC upper bound raised to 1.0% as a flexible ceiling.",
     "label": "Rates held (YCC adjusted)"},
    {"date": "2023-09-22", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2023-10-31", "decision": "hold", "rate": "-0.10%",
     "note": "YCC further loosened; 1% ceiling made reference rather than hard cap.",
     "label": "Rates held (YCC loosened)"},
    {"date": "2023-12-19", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
]

BOJ_MEETINGS_2024 = [
    {"date": "2024-01-23", "decision": "hold", "rate": "-0.10%", "label": "Rates held"},
    {"date": "2024-03-19", "decision": "hike", "rate": "0.10%",
     "note": "Ended NIRP. First rate hike since 2007. YCC abolished. 8–1 majority.",
     "label": "+20bp hike · first hike since 2007"},
    {"date": "2024-04-26", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2024-06-14", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2024-07-31", "decision": "hike", "rate": "0.25%",
     "note": "7–2 majority. Also began reducing JGB purchases.",
     "label": "+15bp hike · 7–2"},
    {"date": "2024-09-20", "decision": "hold", "rate": "0.25%", "label": "Rates held"},
    {"date": "2024-10-31", "decision": "hold", "rate": "0.25%", "label": "Rates held"},
    {"date": "2024-12-19", "decision": "hold", "rate": "0.25%", "label": "Rates held"},
]

BOJ_MEETINGS_2025 = [
    {"date": "2025-01-24", "decision": "hike", "rate": "0.50%",
     "note": "8–1 majority.",
     "label": "+25bp hike · 8–1"},
    {"date": "2025-03-19", "decision": "hold", "rate": "0.50%", "label": "Rates held"},
    {"date": "2025-04-30", "decision": "hold", "rate": "0.50%",
     "note": "Held amid global trade uncertainty. Lowered growth forecasts.",
     "label": "Rates held"},
    {"date": "2025-06-17", "decision": "hold", "rate": "0.50%", "label": "Rates held"},
    {"date": "2025-07-31", "decision": "hold", "rate": "0.50%", "label": "Rates held"},
    {"date": "2025-09-19", "decision": "hold", "rate": "0.50%", "label": "Rates held"},
    {"date": "2025-10-29", "decision": "hold", "rate": "0.50%",
     "note": "Held; two board members dissented, preferring a hike.",
     "label": "Rates held"},
    {"date": "2025-12-19", "decision": "hike", "rate": "0.75%",
     "note": "Unanimous +25bp. Highest since 1995.",
     "label": "+25bp hike"},
]

BOJ_MEETINGS_2026 = [
    {"date": "2026-01-23", "decision": "hold", "rate": "0.75%",
     "note": "Takata dissented, proposed a +25bp hike to 1.00%.",
     "label": "Rates held"},
    {"date": "2026-03-19", "decision": "hold", "rate": "0.75%", "label": "Rates held"},
    {"date": "2026-04-28", "decision": "hold", "rate": "0.75%", "label": "Rates held"},
    {"date": "2026-06-16", "decision": "hike", "rate": "1.00%",
     "note": "7–1; Asada dissented (preferred hold). Highest since Sept 1995.",
     "label": "+25bp hike · 7–1"},
    {"date": "2026-07-31", "decision": "upcoming", "label": "Jul 31"},
    {"date": "2026-09-19", "decision": "upcoming", "label": "Sep 19"},
    {"date": "2026-10-29", "decision": "upcoming", "label": "Oct 29"},
    {"date": "2026-12-18", "decision": "upcoming", "label": "Dec 18"},
]

BOJ_MEETINGS = (
    BOJ_MEETINGS_2021 + BOJ_MEETINGS_2022 + BOJ_MEETINGS_2023 +
    BOJ_MEETINGS_2024 + BOJ_MEETINGS_2025 + BOJ_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# BRAZIL (BCB / COPOM) — 8 meetings per year, ~6-week intervals
# Dates are the second day (decision day) of each two-day meeting.
# Sources: bcb.gov.br/en/monetarypolicy/copomresolutions
# ---------------------------------------------------------------------------

COPOM_MEETINGS_2021 = [
    {"date": "2021-01-20", "decision": "hike", "rate": "2.00%",  "label": "+75bp hike"},
    {"date": "2021-03-17", "decision": "hike", "rate": "2.75%",  "label": "+75bp hike"},
    {"date": "2021-05-05", "decision": "hike", "rate": "3.50%",  "label": "+75bp hike"},
    {"date": "2021-06-16", "decision": "hike", "rate": "4.25%",  "label": "+75bp hike"},
    {"date": "2021-08-04", "decision": "hike", "rate": "5.25%",  "label": "+100bp hike"},
    {"date": "2021-09-22", "decision": "hike", "rate": "6.25%",  "label": "+100bp hike"},
    {"date": "2021-10-27", "decision": "hike", "rate": "7.75%",  "label": "+150bp hike"},
    {"date": "2021-12-08", "decision": "hike", "rate": "9.25%",  "label": "+150bp hike"},
]

COPOM_MEETINGS_2022 = [
    {"date": "2022-02-02", "decision": "hike", "rate": "10.75%", "label": "+150bp hike"},
    {"date": "2022-03-16", "decision": "hike", "rate": "11.75%", "label": "+100bp hike"},
    {"date": "2022-05-04", "decision": "hike", "rate": "12.75%", "label": "+100bp hike"},
    {"date": "2022-06-15", "decision": "hike", "rate": "13.25%", "label": "+50bp hike"},
    {"date": "2022-08-03", "decision": "hike", "rate": "13.75%", "label": "+50bp hike"},
    {"date": "2022-09-21", "decision": "hold", "rate": "13.75%", "label": "Rates held"},
    {"date": "2022-10-26", "decision": "hold", "rate": "13.75%", "label": "Rates held"},
    {"date": "2022-12-07", "decision": "hold", "rate": "13.75%", "label": "Rates held"},
]

COPOM_MEETINGS_2023 = [
    {"date": "2023-02-01", "decision": "hold", "rate": "13.75%", "label": "Rates held"},
    {"date": "2023-03-22", "decision": "hold", "rate": "13.75%", "label": "Rates held"},
    {"date": "2023-05-03", "decision": "cut",  "rate": "13.25%", "label": "-50bp cut"},
    {"date": "2023-06-21", "decision": "cut",  "rate": "13.00%", "label": "-25bp cut · 5-4"},
    {"date": "2023-08-02", "decision": "cut",  "rate": "12.75%", "label": "-50bp cut"},
    {"date": "2023-09-20", "decision": "cut",  "rate": "12.25%", "label": "-50bp cut"},
    {"date": "2023-11-01", "decision": "cut",  "rate": "11.75%", "label": "-50bp cut"},
    {"date": "2023-12-13", "decision": "cut",  "rate": "11.25%", "label": "-50bp cut"},
]

COPOM_MEETINGS_2024 = [
    {"date": "2024-01-31", "decision": "cut",  "rate": "11.00%", "label": "-50bp cut"},
    {"date": "2024-03-20", "decision": "cut",  "rate": "10.75%", "label": "-50bp cut"},
    {"date": "2024-05-08", "decision": "cut",  "rate": "10.50%", "label": "-25bp cut · 5-4"},
    {"date": "2024-06-19", "decision": "hold", "rate": "10.50%", "label": "Rates held"},
    {"date": "2024-07-31", "decision": "hold", "rate": "10.50%", "label": "Rates held"},
    {"date": "2024-09-18", "decision": "hike", "rate": "10.75%", "label": "+25bp hike"},
    {"date": "2024-11-06", "decision": "hike", "rate": "11.25%", "label": "+50bp hike"},
    {"date": "2024-12-11", "decision": "hike", "rate": "12.25%", "label": "+100bp hike"},
]

COPOM_MEETINGS_2025 = [
    {"date": "2025-01-29", "decision": "hike", "rate": "13.25%", "label": "+100bp hike"},
    {"date": "2025-03-19", "decision": "hike", "rate": "14.25%", "label": "+100bp hike"},
    {"date": "2025-05-07", "decision": "hold", "rate": "14.25%", "label": "Rates held"},
    {"date": "2025-06-18", "decision": "hold", "rate": "14.25%", "label": "Rates held"},
    {"date": "2025-07-30", "decision": "upcoming", "label": "Jul 30"},
    {"date": "2025-09-17", "decision": "upcoming", "label": "Sep 17"},
    {"date": "2025-11-05", "decision": "upcoming", "label": "Nov 5"},
    {"date": "2025-12-10", "decision": "upcoming", "label": "Dec 10"},
]

COPOM_MEETINGS_2026 = [
    {"date": "2026-01-28", "decision": "hold", "rate": "14.25%", "label": "Rates held"},
    {"date": "2026-03-19", "decision": "hold", "rate": "14.25%", "label": "Rates held"},
    {"date": "2026-05-07", "decision": "hold", "rate": "14.25%", "label": "Rates held"},
    {"date": "2026-06-18", "decision": "hold", "rate": "14.25%", "label": "Rates held"},
    {"date": "2026-07-30", "decision": "upcoming", "label": "Jul 30"},
    {"date": "2026-09-17", "decision": "upcoming", "label": "Sep 17"},
    {"date": "2026-11-04", "decision": "upcoming", "label": "Nov 4"},
    {"date": "2026-12-09", "decision": "upcoming", "label": "Dec 9"},
]

COPOM_MEETINGS = (
    COPOM_MEETINGS_2021 + COPOM_MEETINGS_2022 + COPOM_MEETINGS_2023 +
    COPOM_MEETINGS_2024 + COPOM_MEETINGS_2025 + COPOM_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# Riksbank (Sveriges Riksbank) — 6 meetings/year
# ---------------------------------------------------------------------------

RIKSBANK_MEETINGS_2021 = [
    {"date": "2021-02-10", "decision": "hold", "rate": "0.00%", "label": "Rates held"},
    {"date": "2021-04-27", "decision": "hold", "rate": "0.00%", "label": "Rates held"},
    {"date": "2021-06-30", "decision": "hold", "rate": "0.00%", "label": "Rates held"},
    {"date": "2021-09-21", "decision": "hold", "rate": "0.00%", "label": "Rates held"},
    {"date": "2021-11-23", "decision": "hold", "rate": "0.00%", "label": "Rates held"},
]

RIKSBANK_MEETINGS_2022 = [
    {"date": "2022-02-09", "decision": "hold", "rate": "0.00%", "label": "Rates held"},
    {"date": "2022-04-27", "decision": "hike", "rate": "0.25%", "label": "+25bp hike"},
    {"date": "2022-06-30", "decision": "hike", "rate": "0.75%", "label": "+50bp hike"},
    {"date": "2022-09-20", "decision": "hike", "rate": "1.75%", "label": "+100bp hike"},
    {"date": "2022-11-23", "decision": "hike", "rate": "2.50%", "label": "+75bp hike"},
]

RIKSBANK_MEETINGS_2023 = [
    {"date": "2023-02-08", "decision": "hike", "rate": "3.00%", "label": "+50bp hike"},
    {"date": "2023-04-26", "decision": "hike", "rate": "3.50%", "label": "+50bp hike"},
    {"date": "2023-06-29", "decision": "hike", "rate": "3.75%", "label": "+25bp hike"},
    {"date": "2023-09-20", "decision": "hike", "rate": "4.00%", "label": "+25bp hike"},
    {"date": "2023-11-22", "decision": "hold", "rate": "4.00%", "label": "Rates held"},
]

RIKSBANK_MEETINGS_2024 = [
    {"date": "2024-02-01", "decision": "hold", "rate": "4.00%", "label": "Rates held"},
    {"date": "2024-03-27", "decision": "cut",  "rate": "3.75%", "label": "-25bp cut"},
    {"date": "2024-05-08", "decision": "cut",  "rate": "3.50%", "label": "-25bp cut"},
    {"date": "2024-06-26", "decision": "cut",  "rate": "3.50%", "label": "Rates held"},
    {"date": "2024-08-20", "decision": "cut",  "rate": "3.25%", "label": "-25bp cut"},
    {"date": "2024-11-06", "decision": "cut",  "rate": "2.75%", "label": "-50bp cut"},
]

RIKSBANK_MEETINGS_2025 = [
    {"date": "2025-01-29", "decision": "cut",  "rate": "2.50%", "label": "-25bp cut"},
    {"date": "2025-03-19", "decision": "cut",  "rate": "2.25%", "label": "-25bp cut"},
    {"date": "2025-04-30", "decision": "hold", "rate": "2.25%", "label": "Rates held"},
    {"date": "2025-06-18", "decision": "hold", "rate": "2.25%", "label": "Rates held"},
    {"date": "2025-09-10", "decision": "upcoming", "label": "Sep 10"},
    {"date": "2025-11-05", "decision": "upcoming", "label": "Nov 5"},
]

RIKSBANK_MEETINGS_2026 = [
    {"date": "2026-02-04", "decision": "hold", "rate": "2.25%", "label": "Rates held"},
    {"date": "2026-03-25", "decision": "hold", "rate": "2.25%", "label": "Rates held"},
    {"date": "2026-04-29", "decision": "hold", "rate": "2.25%", "label": "Rates held"},
    {"date": "2026-06-17", "decision": "hold", "rate": "2.25%", "label": "Rates held"},
    {"date": "2026-09-09", "decision": "upcoming", "label": "Sep 9"},
    {"date": "2026-11-04", "decision": "upcoming", "label": "Nov 4"},
]

RIKSBANK_MEETINGS = (
    RIKSBANK_MEETINGS_2021 + RIKSBANK_MEETINGS_2022 + RIKSBANK_MEETINGS_2023 +
    RIKSBANK_MEETINGS_2024 + RIKSBANK_MEETINGS_2025 + RIKSBANK_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# SARB (South African Reserve Bank) — MPC meets 6x/year
# ---------------------------------------------------------------------------

SARB_MEETINGS_2021 = [
    {"date": "2021-01-28", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2021-03-25", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2021-05-20", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2021-07-22", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2021-09-23", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2021-11-18", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
]

SARB_MEETINGS_2022 = [
    {"date": "2022-01-27", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2022-03-24", "decision": "hike", "rate": "4.00%", "label": "+25bp hike"},
    {"date": "2022-05-19", "decision": "hike", "rate": "4.75%", "label": "+50bp hike"},
    {"date": "2022-07-21", "decision": "hike", "rate": "5.50%", "label": "+75bp hike"},
    {"date": "2022-09-22", "decision": "hike", "rate": "6.25%", "label": "+75bp hike"},
    {"date": "2022-11-24", "decision": "hike", "rate": "7.00%", "label": "+75bp hike"},
]

SARB_MEETINGS_2023 = [
    {"date": "2023-01-26", "decision": "hike", "rate": "7.25%", "label": "+25bp hike"},
    {"date": "2023-03-30", "decision": "hike", "rate": "7.75%", "label": "+50bp hike"},
    {"date": "2023-05-25", "decision": "hike", "rate": "8.25%", "label": "+50bp hike"},
    {"date": "2023-07-20", "decision": "hold", "rate": "8.25%", "label": "Rates held"},
    {"date": "2023-09-21", "decision": "hold", "rate": "8.25%", "label": "Rates held"},
    {"date": "2023-11-23", "decision": "hold", "rate": "8.25%", "label": "Rates held"},
]

SARB_MEETINGS_2024 = [
    {"date": "2024-01-25", "decision": "hold", "rate": "8.25%", "label": "Rates held"},
    {"date": "2024-03-28", "decision": "hold", "rate": "8.25%", "label": "Rates held"},
    {"date": "2024-05-30", "decision": "hold", "rate": "8.25%", "label": "Rates held"},
    {"date": "2024-07-18", "decision": "hold", "rate": "8.25%", "label": "Rates held"},
    {"date": "2024-09-19", "decision": "cut",  "rate": "8.00%", "label": "-25bp cut"},
    {"date": "2024-11-21", "decision": "cut",  "rate": "7.75%", "label": "-25bp cut"},
]

SARB_MEETINGS_2025 = [
    {"date": "2025-01-30", "decision": "cut",  "rate": "7.50%", "label": "-25bp cut"},
    {"date": "2025-03-27", "decision": "hold", "rate": "7.50%", "label": "Rates held"},
    {"date": "2025-05-29", "decision": "hold", "rate": "7.50%", "label": "Rates held"},
    {"date": "2025-07-17", "decision": "hold", "rate": "7.50%", "label": "Rates held"},
    {"date": "2025-09-18", "decision": "hold", "rate": "7.50%", "label": "Rates held"},
    {"date": "2025-11-20", "decision": "cut",  "rate": "7.25%", "label": "-25bp cut"},
]

SARB_MEETINGS_2026 = [
    {"date": "2026-01-30", "decision": "hold", "rate": "7.25%", "label": "Rates held"},
    {"date": "2026-03-27", "decision": "hold", "rate": "7.25%", "label": "Rates held"},
    {"date": "2026-05-29", "decision": "cut",  "rate": "7.00%", "label": "-25bp cut"},
    {"date": "2026-07-17", "decision": "upcoming", "label": "Jul 17"},
    {"date": "2026-09-17", "decision": "upcoming", "label": "Sep 17"},
    {"date": "2026-11-19", "decision": "upcoming", "label": "Nov 19"},
]

SARB_MEETINGS = (
    SARB_MEETINGS_2021 + SARB_MEETINGS_2022 + SARB_MEETINGS_2023 +
    SARB_MEETINGS_2024 + SARB_MEETINGS_2025 + SARB_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# CNB (Czech National Bank) — Bank Board meets 8x/year
# CNB was among the most hawkish CBs in 2021-2022, peaking at 7.00%
# ---------------------------------------------------------------------------

CNB_MEETINGS_2021 = [
    {"date": "2021-02-04", "decision": "hold", "rate": "0.25%", "label": "Rates held"},
    {"date": "2021-03-25", "decision": "hold", "rate": "0.25%", "label": "Rates held"},
    {"date": "2021-05-06", "decision": "hold", "rate": "0.25%", "label": "Rates held"},
    {"date": "2021-06-23", "decision": "hike", "rate": "0.50%", "label": "+25bp hike"},
    {"date": "2021-08-05", "decision": "hike", "rate": "0.75%", "label": "+25bp hike"},
    {"date": "2021-09-23", "decision": "hike", "rate": "1.50%", "label": "+75bp hike"},
    {"date": "2021-11-04", "decision": "hike", "rate": "2.75%", "label": "+125bp hike"},
    {"date": "2021-12-22", "decision": "hike", "rate": "3.75%", "label": "+100bp hike"},
]

CNB_MEETINGS_2022 = [
    {"date": "2022-02-03", "decision": "hike", "rate": "4.50%", "label": "+75bp hike"},
    {"date": "2022-03-31", "decision": "hike", "rate": "5.00%", "label": "+50bp hike"},
    {"date": "2022-05-05", "decision": "hike", "rate": "5.75%", "label": "+75bp hike"},
    {"date": "2022-06-22", "decision": "hike", "rate": "7.00%", "label": "+125bp hike"},
    {"date": "2022-08-04", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2022-09-29", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2022-11-03", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2022-12-21", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
]

CNB_MEETINGS_2023 = [
    {"date": "2023-02-02", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-03-30", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-05-04", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-06-22", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-08-03", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-09-28", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-11-02", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-12-21", "decision": "cut",  "rate": "6.75%", "label": "-25bp cut"},
]

CNB_MEETINGS_2024 = [
    {"date": "2024-02-08", "decision": "cut",  "rate": "6.25%", "label": "-50bp cut"},
    {"date": "2024-03-20", "decision": "cut",  "rate": "5.75%", "label": "-50bp cut"},
    {"date": "2024-05-02", "decision": "cut",  "rate": "5.25%", "label": "-50bp cut"},
    {"date": "2024-06-20", "decision": "cut",  "rate": "4.75%", "label": "-50bp cut"},
    {"date": "2024-08-01", "decision": "cut",  "rate": "4.50%", "label": "-25bp cut"},
    {"date": "2024-09-26", "decision": "cut",  "rate": "4.25%", "label": "-25bp cut"},
    {"date": "2024-11-07", "decision": "cut",  "rate": "4.00%", "label": "-25bp cut"},
    {"date": "2024-12-19", "decision": "cut",  "rate": "3.75%", "label": "-25bp cut"},
]

CNB_MEETINGS_2025 = [
    {"date": "2025-02-06", "decision": "cut",  "rate": "3.50%", "label": "-25bp cut"},
    {"date": "2025-03-27", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2025-05-08", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2025-06-19", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2025-08-07", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2025-09-18", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2025-11-06", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2025-12-18", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
]

CNB_MEETINGS_2026 = [
    {"date": "2026-02-05", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2026-03-19", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2026-05-07", "decision": "hold", "rate": "3.50%", "label": "Rates held"},
    {"date": "2026-06-18", "decision": "hike", "rate": "3.75%", "label": "+25bp hike"},
    {"date": "2026-08-06", "decision": "upcoming", "label": "Aug 6"},
    {"date": "2026-09-17", "decision": "upcoming", "label": "Sep 17"},
    {"date": "2026-11-05", "decision": "upcoming", "label": "Nov 5"},
    {"date": "2026-12-17", "decision": "upcoming", "label": "Dec 17"},
]

CNB_MEETINGS = (
    CNB_MEETINGS_2021 + CNB_MEETINGS_2022 + CNB_MEETINGS_2023 +
    CNB_MEETINGS_2024 + CNB_MEETINGS_2025 + CNB_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# NBP (Narodowy Bank Polski) — Monetary Policy Council (RPP), ~11 meetings/year
# Reference rate (stopa referencyjna)
# ---------------------------------------------------------------------------

NBP_MEETINGS_2021 = [
    {"date": "2021-01-13", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2021-02-03", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2021-03-03", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2021-04-07", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2021-05-05", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2021-06-09", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2021-07-07", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2021-09-08", "decision": "hold", "rate": "0.10%", "label": "Rates held"},
    {"date": "2021-10-06", "decision": "hike", "rate": "0.50%", "label": "+40bp hike"},
    {"date": "2021-11-03", "decision": "hike", "rate": "1.25%", "label": "+75bp hike"},
    {"date": "2021-12-08", "decision": "hike", "rate": "1.75%", "label": "+50bp hike"},
]

NBP_MEETINGS_2022 = [
    {"date": "2022-01-05", "decision": "hike", "rate": "2.25%", "label": "+50bp hike"},
    {"date": "2022-02-09", "decision": "hike", "rate": "2.75%", "label": "+50bp hike"},
    {"date": "2022-03-09", "decision": "hike", "rate": "3.50%", "label": "+75bp hike"},
    {"date": "2022-04-06", "decision": "hike", "rate": "4.50%", "label": "+100bp hike"},
    {"date": "2022-05-05", "decision": "hike", "rate": "5.25%", "label": "+75bp hike"},
    {"date": "2022-06-08", "decision": "hike", "rate": "6.00%", "label": "+75bp hike"},
    {"date": "2022-07-06", "decision": "hike", "rate": "6.50%", "label": "+50bp hike"},
    {"date": "2022-09-07", "decision": "hike", "rate": "6.75%", "label": "+25bp hike"},
    {"date": "2022-10-05", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2022-11-09", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2022-12-07", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
]

NBP_MEETINGS_2023 = [
    {"date": "2023-01-11", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2023-02-08", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2023-03-08", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2023-04-05", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2023-05-10", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2023-06-07", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2023-07-05", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2023-09-06", "decision": "cut",  "rate": "6.00%", "label": "-75bp cut"},
    {"date": "2023-10-04", "decision": "cut",  "rate": "5.75%", "label": "-25bp cut"},
    {"date": "2023-11-08", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2023-12-06", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
]

NBP_MEETINGS_2024 = [
    {"date": "2024-01-10", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-02-07", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-03-06", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-04-03", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-05-08", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-06-05", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-07-03", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-09-04", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-10-02", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-11-06", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2024-12-04", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
]

NBP_MEETINGS_2025 = [
    {"date": "2025-01-15", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2025-02-05", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2025-03-05", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2025-04-02", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2025-05-07", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2025-06-04", "decision": "hold", "rate": "5.75%", "label": "Rates held"},
    {"date": "2025-07-09", "decision": "upcoming", "label": "Jul 9"},
    {"date": "2025-09-03", "decision": "upcoming", "label": "Sep 3"},
    {"date": "2025-10-08", "decision": "upcoming", "label": "Oct 8"},
    {"date": "2025-11-05", "decision": "upcoming", "label": "Nov 5"},
    {"date": "2025-12-03", "decision": "upcoming", "label": "Dec 3"},
]

NBP_MEETINGS_2026 = [
    {"date": "2026-01-14", "decision": "upcoming", "label": "Jan 14"},
    {"date": "2026-02-04", "decision": "upcoming", "label": "Feb 4"},
    {"date": "2026-03-04", "decision": "upcoming", "label": "Mar 4"},
    {"date": "2026-04-01", "decision": "upcoming", "label": "Apr 1"},
    {"date": "2026-05-06", "decision": "upcoming", "label": "May 6"},
    {"date": "2026-06-03", "decision": "upcoming", "label": "Jun 3"},
    {"date": "2026-07-08", "decision": "upcoming", "label": "Jul 8"},
    {"date": "2026-09-02", "decision": "upcoming", "label": "Sep 2"},
    {"date": "2026-10-07", "decision": "upcoming", "label": "Oct 7"},
    {"date": "2026-11-04", "decision": "upcoming", "label": "Nov 4"},
    {"date": "2026-12-02", "decision": "upcoming", "label": "Dec 2"},
]

NBP_MEETINGS = (
    NBP_MEETINGS_2021 + NBP_MEETINGS_2022 + NBP_MEETINGS_2023 +
    NBP_MEETINGS_2024 + NBP_MEETINGS_2025 + NBP_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# BNR (Banca Națională a României) — Board, ~8 meetings/year
# Key policy rate (rata dobânzii de politică monetară)
# ---------------------------------------------------------------------------

BNR_MEETINGS_2021 = [
    {"date": "2021-01-15", "decision": "hold", "rate": "1.25%", "label": "Rates held"},
    {"date": "2021-03-15", "decision": "hold", "rate": "1.25%", "label": "Rates held"},
    {"date": "2021-05-12", "decision": "hold", "rate": "1.25%", "label": "Rates held"},
    {"date": "2021-07-07", "decision": "hold", "rate": "1.25%", "label": "Rates held"},
    {"date": "2021-08-06", "decision": "hike", "rate": "1.50%", "label": "+25bp hike"},
    {"date": "2021-10-05", "decision": "hike", "rate": "1.75%", "label": "+25bp hike"},
    {"date": "2021-11-09", "decision": "hike", "rate": "1.75%", "label": "Rates held"},
    {"date": "2021-12-10", "decision": "hold", "rate": "1.75%", "label": "Rates held"},
]

BNR_MEETINGS_2022 = [
    {"date": "2022-01-10", "decision": "hike", "rate": "2.00%", "label": "+25bp hike"},
    {"date": "2022-02-09", "decision": "hike", "rate": "2.50%", "label": "+50bp hike"},
    {"date": "2022-04-05", "decision": "hike", "rate": "3.00%", "label": "+50bp hike"},
    {"date": "2022-05-10", "decision": "hike", "rate": "3.75%", "label": "+75bp hike"},
    {"date": "2022-07-05", "decision": "hike", "rate": "4.75%", "label": "+100bp hike"},
    {"date": "2022-08-05", "decision": "hike", "rate": "5.50%", "label": "+75bp hike"},
    {"date": "2022-10-05", "decision": "hike", "rate": "6.25%", "label": "+75bp hike"},
    {"date": "2022-11-08", "decision": "hike", "rate": "6.75%", "label": "+50bp hike"},
]

BNR_MEETINGS_2023 = [
    {"date": "2023-01-10", "decision": "hike", "rate": "7.00%", "label": "+25bp hike"},
    {"date": "2023-02-07", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-04-04", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-05-09", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-07-04", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-08-08", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-10-10", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2023-11-08", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
]

BNR_MEETINGS_2024 = [
    {"date": "2024-01-09", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2024-02-07", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2024-04-02", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2024-05-07", "decision": "hold", "rate": "7.00%", "label": "Rates held"},
    {"date": "2024-07-05", "decision": "cut",  "rate": "6.75%", "label": "-25bp cut"},
    {"date": "2024-08-06", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2024-10-08", "decision": "hold", "rate": "6.75%", "label": "Rates held"},
    {"date": "2024-11-05", "decision": "cut",  "rate": "6.50%", "label": "-25bp cut"},
]

BNR_MEETINGS_2025 = [
    {"date": "2025-01-14", "decision": "cut",  "rate": "6.25%", "label": "-25bp cut"},
    {"date": "2025-02-11", "decision": "cut",  "rate": "6.00%", "label": "-25bp cut"},
    {"date": "2025-04-08", "decision": "hold", "rate": "6.00%", "label": "Rates held"},
    {"date": "2025-05-13", "decision": "hold", "rate": "6.00%", "label": "Rates held"},
    {"date": "2025-07-08", "decision": "upcoming", "label": "Jul 8"},
    {"date": "2025-08-05", "decision": "upcoming", "label": "Aug 5"},
    {"date": "2025-10-07", "decision": "upcoming", "label": "Oct 7"},
    {"date": "2025-11-11", "decision": "upcoming", "label": "Nov 11"},
]

BNR_MEETINGS_2026 = [
    {"date": "2026-01-13", "decision": "upcoming", "label": "Jan 13"},
    {"date": "2026-02-10", "decision": "upcoming", "label": "Feb 10"},
    {"date": "2026-04-07", "decision": "upcoming", "label": "Apr 7"},
    {"date": "2026-05-12", "decision": "upcoming", "label": "May 12"},
    {"date": "2026-07-07", "decision": "upcoming", "label": "Jul 7"},
    {"date": "2026-08-04", "decision": "upcoming", "label": "Aug 4"},
    {"date": "2026-10-06", "decision": "upcoming", "label": "Oct 6"},
    {"date": "2026-11-10", "decision": "upcoming", "label": "Nov 10"},
]

BNR_MEETINGS = (
    BNR_MEETINGS_2021 + BNR_MEETINGS_2022 + BNR_MEETINGS_2023 +
    BNR_MEETINGS_2024 + BNR_MEETINGS_2025 + BNR_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# CBRT (Central Bank of the Republic of Turkey) — MPC, ~8 meetings/year
# 1-week repo rate (key policy rate)
# ---------------------------------------------------------------------------

CBRT_MEETINGS_2021 = [
    {"date": "2021-01-21", "decision": "hold", "rate": "17.00%", "label": "Rates held"},
    {"date": "2021-02-18", "decision": "hold", "rate": "17.00%", "label": "Rates held"},
    {"date": "2021-03-18", "decision": "cut",  "rate": "19.00%",
     "note": "Rate hiked to 19% then cut under Kavcioglu. Complex period.",
     "label": "+200bp hike then cuts"},
    {"date": "2021-04-15", "decision": "hold", "rate": "19.00%", "label": "Rates held"},
    {"date": "2021-05-06", "decision": "hold", "rate": "19.00%", "label": "Rates held"},
    {"date": "2021-06-17", "decision": "hold", "rate": "19.00%", "label": "Rates held"},
    {"date": "2021-07-15", "decision": "hold", "rate": "19.00%", "label": "Rates held"},
    {"date": "2021-08-12", "decision": "hold", "rate": "19.00%", "label": "Rates held"},
    {"date": "2021-09-23", "decision": "cut",  "rate": "18.00%", "label": "-100bp cut"},
    {"date": "2021-10-21", "decision": "cut",  "rate": "16.00%", "label": "-200bp cut"},
    {"date": "2021-11-18", "decision": "cut",  "rate": "15.00%", "label": "-100bp cut"},
    {"date": "2021-12-16", "decision": "cut",  "rate": "14.00%", "label": "-100bp cut"},
]

CBRT_MEETINGS_2022 = [
    {"date": "2022-01-20", "decision": "hold", "rate": "14.00%", "label": "Rates held"},
    {"date": "2022-02-17", "decision": "hold", "rate": "14.00%", "label": "Rates held"},
    {"date": "2022-03-17", "decision": "hold", "rate": "14.00%", "label": "Rates held"},
    {"date": "2022-04-14", "decision": "hold", "rate": "14.00%", "label": "Rates held"},
    {"date": "2022-05-26", "decision": "hold", "rate": "14.00%", "label": "Rates held"},
    {"date": "2022-06-23", "decision": "hold", "rate": "14.00%", "label": "Rates held"},
    {"date": "2022-07-21", "decision": "cut",  "rate": "13.00%", "label": "-100bp cut"},
    {"date": "2022-08-18", "decision": "cut",  "rate": "12.00%", "label": "-100bp cut"},
    {"date": "2022-09-22", "decision": "cut",  "rate": "11.00%", "label": "-100bp cut"},
    {"date": "2022-10-20", "decision": "hold", "rate": "11.00%", "label": "Rates held"},
    {"date": "2022-11-24", "decision": "hold", "rate": "11.00%", "label": "Rates held"},
    {"date": "2022-12-22", "decision": "hold", "rate": "11.00%", "label": "Rates held"},
]

CBRT_MEETINGS_2023 = [
    {"date": "2023-01-19", "decision": "hold", "rate": "9.00%",  "label": "Rates held"},
    {"date": "2023-02-23", "decision": "cut",  "rate": "8.50%",  "label": "-50bp cut"},
    {"date": "2023-03-23", "decision": "hold", "rate": "8.50%",  "label": "Rates held"},
    {"date": "2023-04-27", "decision": "hold", "rate": "8.50%",  "label": "Rates held"},
    {"date": "2023-05-25", "decision": "hold", "rate": "8.50%",  "label": "Rates held"},
    {"date": "2023-06-22", "decision": "hike", "rate": "15.00%", "label": "+650bp hike (policy reversal)"},
    {"date": "2023-07-20", "decision": "hike", "rate": "17.50%", "label": "+250bp hike"},
    {"date": "2023-08-24", "decision": "hike", "rate": "25.00%", "label": "+750bp hike"},
    {"date": "2023-09-21", "decision": "hike", "rate": "30.00%", "label": "+500bp hike"},
    {"date": "2023-10-26", "decision": "hike", "rate": "35.00%", "label": "+500bp hike"},
    {"date": "2023-11-23", "decision": "hike", "rate": "40.00%", "label": "+500bp hike"},
    {"date": "2023-12-21", "decision": "hike", "rate": "42.50%", "label": "+250bp hike"},
]

CBRT_MEETINGS_2024 = [
    {"date": "2024-01-25", "decision": "hike", "rate": "45.00%", "label": "+250bp hike"},
    {"date": "2024-02-22", "decision": "hike", "rate": "45.00%",
     "note": "Karahan becomes Governor Feb 2024",
     "label": "Rates held (new Governor)"},
    {"date": "2024-03-21", "decision": "hike", "rate": "50.00%", "label": "+500bp hike (peak)"},
    {"date": "2024-04-25", "decision": "hold", "rate": "50.00%", "label": "Rates held"},
    {"date": "2024-05-23", "decision": "hold", "rate": "50.00%", "label": "Rates held"},
    {"date": "2024-06-20", "decision": "hold", "rate": "50.00%", "label": "Rates held"},
    {"date": "2024-07-23", "decision": "hold", "rate": "50.00%", "label": "Rates held"},
    {"date": "2024-09-19", "decision": "hold", "rate": "50.00%", "label": "Rates held"},
    {"date": "2024-10-17", "decision": "hold", "rate": "50.00%", "label": "Rates held"},
    {"date": "2024-11-21", "decision": "cut",  "rate": "47.50%", "label": "-250bp cut"},
    {"date": "2024-12-26", "decision": "cut",  "rate": "45.00%", "label": "-250bp cut"},
]

CBRT_MEETINGS_2025 = [
    {"date": "2025-01-23", "decision": "cut",  "rate": "42.50%", "label": "-250bp cut"},
    {"date": "2025-02-20", "decision": "cut",  "rate": "40.00%", "label": "-250bp cut"},
    {"date": "2025-03-20", "decision": "cut",  "rate": "37.50%", "label": "-250bp cut"},
    {"date": "2025-04-17", "decision": "cut",  "rate": "35.00%", "label": "-250bp cut"},
    {"date": "2025-05-22", "decision": "cut",  "rate": "32.50%", "label": "-250bp cut"},
    {"date": "2025-06-19", "decision": "cut",  "rate": "30.00%", "label": "-250bp cut"},
    {"date": "2025-07-24", "decision": "upcoming", "label": "Jul 24"},
    {"date": "2025-09-18", "decision": "upcoming", "label": "Sep 18"},
    {"date": "2025-10-23", "decision": "upcoming", "label": "Oct 23"},
    {"date": "2025-11-20", "decision": "upcoming", "label": "Nov 20"},
    {"date": "2025-12-25", "decision": "upcoming", "label": "Dec 25"},
]

CBRT_MEETINGS_2026 = [
    {"date": "2026-01-22", "decision": "upcoming", "label": "Jan 22"},
    {"date": "2026-02-19", "decision": "upcoming", "label": "Feb 19"},
    {"date": "2026-03-19", "decision": "upcoming", "label": "Mar 19"},
    {"date": "2026-04-23", "decision": "upcoming", "label": "Apr 23"},
    {"date": "2026-05-21", "decision": "upcoming", "label": "May 21"},
    {"date": "2026-06-18", "decision": "upcoming", "label": "Jun 18"},
    {"date": "2026-07-23", "decision": "upcoming", "label": "Jul 23"},
    {"date": "2026-09-17", "decision": "upcoming", "label": "Sep 17"},
    {"date": "2026-10-22", "decision": "upcoming", "label": "Oct 22"},
    {"date": "2026-11-19", "decision": "upcoming", "label": "Nov 19"},
    {"date": "2026-12-24", "decision": "upcoming", "label": "Dec 24"},
]

CBRT_MEETINGS = (
    CBRT_MEETINGS_2021 + CBRT_MEETINGS_2022 + CBRT_MEETINGS_2023 +
    CBRT_MEETINGS_2024 + CBRT_MEETINGS_2025 + CBRT_MEETINGS_2026
)

# ---------------------------------------------------------------------------
# Accessor — prefer the DB, fall back to the seed lists above
# ---------------------------------------------------------------------------

# Canonical bank name -> the seed list defined above.
_SEED_MEETINGS = {
    "Federal Reserve": FED_MEETINGS,
    "ECB":             ECB_MEETINGS,
    "Bank of England": BOE_MEETINGS,
    "Bank of Japan":   BOJ_MEETINGS,
    "BCB":             COPOM_MEETINGS,
    "Riksbank":        RIKSBANK_MEETINGS,
    "SARB":            SARB_MEETINGS,
    "CNB":             CNB_MEETINGS,
    "NBP":             NBP_MEETINGS,
    "BNR":             BNR_MEETINGS,
    "CBRT":            CBRT_MEETINGS,
}


def get_meetings(bank: str) -> list[dict]:
    """Return the meeting list for a bank, preferring the SQLite `meetings` table.

    Falls back to the hardcoded seed list when the DB has no rows for the bank
    (e.g. fresh checkout, un-seeded DB) or when reading the DB fails. Set
    CB_MEETINGS_NO_DB=1 to force the seed lists (used by the seeding script).
    """
    seed = _SEED_MEETINGS.get(bank, [])
    if os.environ.get("CB_MEETINGS_NO_DB"):
        return seed
    try:
        from meetings_store import load_bank_meetings
        rows = load_bank_meetings(bank)
        return rows if rows else seed
    except Exception:
        return seed

