import os
from pathlib import Path

# Free key from https://help.openalex.org/api/authentication/ ; without one all
# requests share a small daily budget per IP and it runs out quickly.
# Read from the OPENALEX_API_KEY environment variable, or else from the
# git-ignored file .openalex_key next to this script.
_key_file = Path(__file__).parent / ".openalex_key"
API_KEY = os.environ.get("OPENALEX_API_KEY") or (
    _key_file.read_text().strip() if _key_file.exists() else None)

GROUP = 15
EMAIL = "madhuram.ind12@gmail.com"  # sent as mailto= to OpenAlex (polite pool)
YEAR_FROM, YEAR_TO = 2016, 2026

# Looked up via api.openalex.org/institutions?search=... (see README / Step 1)
INSTITUTES = {
    "MANIT Bhopal": {
        "openalex_id": "I91277730",
        "ror": "https://ror.org/026vtd268",
        "official_name": "Maulana Azad National Institute of Technology",
    },
    "NIT Jamshedpur": {
        "openalex_id": "I187761245",
        "ror": "https://ror.org/01sebzx27",
        "official_name": "National Institute of Technology Jamshedpur",
    },
    "NIT Silchar": {
        "openalex_id": "I151903974",
        "ror": "https://ror.org/001ws2a36",
        "official_name": "National Institute of Technology Silchar",
    },
}

# OpenAlex id -> our short name
ID_TO_NAME = {v["openalex_id"]: k for k, v in INSTITUTES.items()}

# Types that are not research output (Step 4 cleaning)
DROP_TYPES = {"paratext", "erratum", "retraction"}

ROOT = Path(__file__).parent
RAW_DIR = ROOT / "data" / "raw"
FACULTY_DIR = ROOT / "data" / "faculty"
OUT_DIR = ROOT / "data" / "out"
