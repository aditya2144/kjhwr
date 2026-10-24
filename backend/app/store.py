"""Load the pre-fetched Elexon snapshot from disk and build the analysis object."""
import pandas as pd

from . import config
from .analysis import WindAnalysis


def load_analysis() -> WindAnalysis:
    for p in (config.ACTUALS_FILE, config.FORECASTS_FILE):
        if not p.exists():
            raise FileNotFoundError(
                f"{p.name} not found in {p.parent}. Run `python backend/scripts/fetch_data.py` once to download "
                "the January 2026 snapshot from Elexon (see README)."
            )
    actuals = pd.read_csv(config.ACTUALS_FILE).rename(columns={"generation": "actual_mw"})
    forecasts = pd.read_csv(config.FORECASTS_FILE).rename(columns={"generation": "forecast_mw"})
    return WindAnalysis(
        actuals, forecasts, config.FIRST_DELIVERY, config.LAST_DELIVERY,
        band_pcts=(config.BAND_LOW_PCT, config.BAND_HIGH_PCT),
    )
