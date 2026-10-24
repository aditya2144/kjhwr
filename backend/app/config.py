"""Central configuration. Everything that is an *assumption* lives here."""
import os
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[1] / "data"))
ACTUALS_FILE = DATA_DIR / "wind_actuals.csv.gz"
FORECASTS_FILE = DATA_DIR / "wind_forecasts.csv.gz"

ELEXON_BASE = "https://data.elexon.co.uk/bmrs/api/v1"

# Scope of the challenge: purchase decisions made in January 2026.
# A decision made on day D is for delivery on day D+1 (day-ahead market).
DECISION_START = date(2026, 1, 1)
DECISION_END = date(2026, 1, 31)
FIRST_DELIVERY = DECISION_START + timedelta(days=1)  # 2 Jan 2026
LAST_DELIVERY = DECISION_END + timedelta(days=1)     # 1 Feb 2026

# ASSUMPTION: the buying team finalises its day-ahead bids at this London
# local time on day D. Configurable in the UI; change the default here.
DEFAULT_CUTOFF = os.getenv("DEFAULT_CUTOFF", "09:00")
CUTOFF_OPTIONS = ["06:00", "09:00", "12:00"]

# Uncertainty band shown around the forecast (percentiles of past error).
BAND_LOW_PCT = 5
BAND_HIGH_PCT = 95

# Raw data we need to fetch (a little before the window for the baseline).
ACTUALS_FETCH_FROM = date(2025, 12, 31)
FORECAST_PUBLISH_FROM = date(2025, 12, 30)
