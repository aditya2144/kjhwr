"""Download the January-2026 wind actuals and forecasts from Elexon into backend/data/.

Run once (needs internet):   python backend/scripts/fetch_data.py
The two small files it writes are committed to the repo so the deployed app
needs no live API calls and every reviewer sees identical numbers.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.app import config                      # noqa: E402
from backend.app.elexon import fetch_actuals, fetch_forecasts  # noqa: E402


def main() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("Fetching actual wind generation (FUELHH)...")
    actuals = fetch_actuals(config.ACTUALS_FETCH_FROM, config.LAST_DELIVERY)
    actuals.to_csv(config.ACTUALS_FILE, index=False, compression="gzip")

    print("Fetching wind forecasts (WINDFOR)...")
    forecasts = fetch_forecasts(config.FORECAST_PUBLISH_FROM, date(2026, 1, 31))
    forecasts.to_csv(config.FORECASTS_FILE, index=False, compression="gzip")

    # ---- sanity report: paste this output into the README / tell Claude if anything looks odd
    print("\n=== Sanity report ===")
    print(f"actuals   : {len(actuals):>7} rows  {actuals.startTime.min()} -> {actuals.startTime.max()}")
    expected = (config.LAST_DELIVERY - config.ACTUALS_FETCH_FROM).days * 48 + 48
    print(f"            expected about {expected} half-hours; missing ~{expected - len(actuals)}")
    print(f"            generation MW: min {actuals.generation.min():.0f}, max {actuals.generation.max():.0f}")
    print(f"forecasts : {len(forecasts):>7} rows  published {forecasts.publishTime.min()} -> {forecasts.publishTime.max()}")
    h = (forecasts.startTime - forecasts.publishTime).dt.total_seconds() / 3600
    print(f"            horizon hours: min {h.min():.1f}, median {h.median():.1f}, max {h.max():.1f}")
    print(f"            distinct publish times: {forecasts.publishTime.nunique()}")
    print(f"\nWrote {config.ACTUALS_FILE.name} and {config.FORECASTS_FILE.name} to {config.DATA_DIR}")


if __name__ == "__main__":
    main()
