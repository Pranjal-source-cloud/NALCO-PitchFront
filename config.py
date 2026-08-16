"""
Configuration for the NALCO Anode Baking Furnace Pitch Front
Digital Tracking System.

All furnace/fire/section constants live here so the rest of the
application never hard-codes them.
"""

import os

from dotenv import load_dotenv

# Load variables from a local .env file (if present) into the process
# environment. In production (Streamlit Cloud, etc.) there is usually no
# .env file — DATABASE_URL is provided directly via platform Secrets/env
# vars instead, and load_dotenv() is a harmless no-op in that case.
load_dotenv()

# ---------------------------------------------------------------------------
# Furnace / Fire configuration
# ---------------------------------------------------------------------------

FURNACES = {
    "ABF-II": {
        "total_sections": 58,
        "fires": ["Fire-1", "Fire-2", "Fire-3"],
    },
    "ABF-III": {
        "total_sections": 40,
        "fires": ["Fire-4", "Fire-5"],
    },
}

FIRE_TO_FURNACE = {}
for _furnace_name, _cfg in FURNACES.items():
    for _fire in _cfg["fires"]:
        FIRE_TO_FURNACE[_fire] = _furnace_name

ALL_FIRES = list(FIRE_TO_FURNACE.keys())

# ---------------------------------------------------------------------------
# FW / Pitch-front configuration
# ---------------------------------------------------------------------------

FW_COUNT = 9
FW_LIST = [f"FW{i}" for i in range(1, FW_COUNT + 1)]

P_OPTIONS = ["P1", "P2", "P3", "P4"]
NO_PITCH_FRONT = "No Pitch Front"
PLACEHOLDER_CHOICE = "-- Select --"
PITCH_FRONT_CHOICES = [PLACEHOLDER_CHOICE] + P_OPTIONS + [NO_PITCH_FRONT]

# Roles within the 3-section profile attached to every FW:
#   section_1 -> exhaust ramp section       (NO pitch-front input, display only)
#   section_2 -> first preceding section    (circular -1, pitch-front input)
#   section_3 -> second preceding section   (circular -2, pitch-front input)
SECTION_ROLES = ["section_1", "section_2", "section_3"]
INPUT_SECTION_ROLES = ["section_2", "section_3"]

# ---------------------------------------------------------------------------
# Remarks
# ---------------------------------------------------------------------------

REMARK_TYPES = ["Normal", "Abnormal", "Observation", "Maintenance", "Other"]

# ---------------------------------------------------------------------------
# Record status
# ---------------------------------------------------------------------------

STATUS_DRAFT = "DRAFT"
STATUS_LOCKED = "LOCKED"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Production is intended to run against a central cloud database (Postgres /
# Supabase) so Shift Incharges on different mobile networks all read/write
# the same data. DATABASE_URL, when set, always takes priority.
# A local SQLite file is used only as a local-development fallback.

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
LOCAL_SQLITE_PATH = os.environ.get("LOCAL_SQLITE_PATH", "nalco_pitchfront.db")

APP_TITLE = "NALCO Anode Baking Furnace — Pitch Front Digital Tracking"
