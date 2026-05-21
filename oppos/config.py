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

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

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
