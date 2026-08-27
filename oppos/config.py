import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=True)

SAM_GOV_API_KEY = os.environ.get("SAM_GOV_API_KEY", "")
SAM_GOV_BASE_URL = "https://api.sam.gov/opportunities/v2/search"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SCORING_MODEL_STAGE1 = os.environ.get("SCORING_MODEL_STAGE1", "claude-haiku-4-5-20251001")
SCORING_MODEL_STAGE2 = os.environ.get("SCORING_MODEL_STAGE2", "claude-sonnet-4-6")

NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")
NOTION_DATASOURCE_ID = os.environ.get("NOTION_DATASOURCE_ID", "b43f162e-0dac-4e66-aeb5-664d6b5296a5")

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY", "")
GOOGLE_CSE_CX = os.environ.get("GOOGLE_CSE_CX", "")  # Programmable Search Engine ID
GOOGLE_CSE_DAILY_LIMIT = int(os.environ.get("GOOGLE_CSE_DAILY_LIMIT", "100"))

NUTRIENT_API_KEY = os.environ.get("NUTRIENT_API_KEY", "")

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "oppos.db"

TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")

STAGE1_FIT_THRESHOLD = 0.5
STAGE2_MIN_SCORE = 40
SLACK_ALERT_MIN_SCORE = 65

ENABLED_SOURCES: list[str] = [
    s.strip()
    for s in os.environ.get("ENABLED_SOURCES", "sam_gov").split(",")
    if s.strip()
]

SOURCE_STATE_MAP: dict[str, str] = {
    "sam_gov": "Federal",
    # Periscope/SOVRA (8)
    "nevada_epro": "Nevada",
    "massachusetts_commbuys": "Massachusetts",
    "new_jersey_njstart": "New Jersey",
    "illinois_bidbuy": "Illinois",
    "oregon_oregonbuys": "Oregon",
    "arkansas_arbuy": "Arkansas",
    "arizona_app": "Arizona",
    "california_caleprocure": "California",
    # JAGGAER/SciQuest (5)
    "iowa_impacs": "Iowa",
    "montana_emacs": "Montana",
    "new_mexico_epronm": "New Mexico",
    "pennsylvania_emarketplace": "Pennsylvania",
    "utah_u3p": "Utah",
    # CGI Advantage VSS (6)
    "west_virginia_wvoasis": "West Virginia",
    "kentucky_emars": "Kentucky",
    "colorado_vss": "Colorado",
    "michigan_sigma": "Michigan",
    "alaska_iris": "Alaska",
    "maine_vss": "Maine",
    # PeopleSoft/Oracle (8)
    "tennessee_edison": "Tennessee",
    "georgia_tgm": "Georgia",
    "indiana_idoa": "Indiana",
    "kansas_esupplier": "Kansas",
    "minnesota_swift": "Minnesota",
    "oklahoma_omes": "Oklahoma",
    "wisconsin_esupplier": "Wisconsin",
    "new_york_sfs": "New York",
    # Ivalua (6)
    "maryland_emma": "Maryland",
    "virginia_eva": "Virginia",
    "north_dakota_ndbuys": "North Dakota",
    "vermont_vtbuys": "Vermont",
    "alabama_alabamabuys": "Alabama",
    "ohio_ohiobuys": "Ohio",
    # SAP/Ariba (5)
    "florida_mfmp": "Florida",
    "north_carolina_evp": "North Carolina",
    "mississippi_magic": "Mississippi",
    "south_carolina_scpro": "South Carolina",
    "louisiana_lapac": "Louisiana",
    # PROACTIS/WebProcure (3)
    "connecticut_ctsource": "Connecticut",
    "missouri_missouribuys": "Missouri",
    "rhode_island_osp": "Rhode Island",
    # Aggregators & private sector sources
    "starbridge": "",
    "google_cse": "",
    "target_accounts": "",
}
