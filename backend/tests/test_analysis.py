"""Unit tests (stdlib unittest, run with: python -m unittest discover -s backend/tests -t .)."""
import json
import unittest
from datetime import date

import numpy as np
import pandas as pd

from backend.app.analysis import (WindAnalysis, compute_metrics, cutoff_for, day_targets, uncertainty_band)


def synthetic(first=date(2026, 1, 2), last=date(2026, 1, 6), hourly=False):
    """Actuals half-hourly; forecasts published hourly, 48h ahead,
    forecast = actual + 100 + 10*horizon_h  (so the error is known exactly)."""
    t = pd.date_range("2025-12-28", "2026-01-10", freq="30min", tz="UTC")
    actual = 5000 + 2000 * np.sin(np.arange(len(t)) / 20.0)
    actuals = pd.DataFrame({"startTime": t, "actual_mw": actual})
    amap = dict(zip(t, actual))
    rows = []
    for pub in pd.date_range("2025-12-28", "2026-01-08", freq="1h", tz="UTC"):
        for k in range(1, 97):  # 48 hours of half-hours
            st = pub + pd.Timedelta(minutes=30 * k)
            if st in amap and (not hourly or st.minute == 0):
                h = (st - pub).total_seconds() / 3600
                rows.append((st, pub, amap[st] + 100 + 10 * h))
    forecasts = pd.DataFrame(rows, columns=["startTime", "publishTime", "forecast_mw"])
    return WindAnalysis(actuals, forecasts, first, last)


class TestHelpers(unittest.TestCase):
    def test_cutoff_is_previous_day_london_time(self):
        c = cutoff_for(date(2026, 1, 15), "09:00")
        self.assertEqual(str(c), "2026-01-14 09:00:00+00:00")  # January: London == UTC

    def test_cutoff_respects_bst(self):
        c = cutoff_for(date(2026, 7, 15), "09:00")
        self.assertEqual(str(c), "2026-07-14 08:00:00+00:00")

    def test_48_periods_in_a_normal_day(self):
        self.assertEqual(len(day_targets(date(2026, 1, 15))), 48)

    def test_dst_day_lengths(self):
        self.assertEqual(len(day_targets(date(2026, 3, 29))), 46)
        self.assertEqual(len(day_targets(date(2026, 10, 25))), 50)

    def test_metrics_known_values(self):
        df = pd.DataFrame({"error_mw": [100.0, -100.0, 300.0, -300.0], "actual_mw": [1000.0] * 4})
        m = compute_metrics(df)
        self.assertEqual(m["mae_mw"], 200.0)
        self.assertEqual(m["bias_mw"], 0.0)
        self.assertAlmostEqual(m["rmse_mw"], np.sqrt((1e4 + 1e4 + 9e4 + 9e4) / 4), places=1)
        self.assertEqual(m["wape_pct"], 20.0)

    def test_band_direction(self):
        # forecasts were historically too high by 200-400 MW -> actual expected lower
        lo, hi, q_lo, q_hi = uncertainty_band(pd.Series([3000.0]), np.array([200.0, 300.0, 400.0]), 5, 95)
        self.assertLess(lo.iloc[0], 3000.0)
        self.assertLess(hi.iloc[0], 3000.0)
        self.assertGreater(q_hi, q_lo)


class TestDecisionLogic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wa = synthetic()

    def test_uses_latest_forecast_at_or_before_cutoff(self):
        v = self.wa.decision_view(date(2026, 1, 3), "09:00")
        first = v["series"][0]
        self.assertEqual(first["published"], "2026-01-02T09:00:00Z")  # cutoff itself is allowed
        self.assertEqual(first["horizon_h"], 15.0)                    # 09:00 -> 00:00 next day
        self.assertEqual(v["series"][-1]["horizon_h"], 38.5)

    def test_never_uses_forecast_published_after_cutoff(self):
        v = self.wa.decision_view(date(2026, 1, 4), "09:00")
        for r in v["series"]:
            self.assertLessEqual(r["published"], v["cutoff_utc"])

    def test_error_is_forecast_minus_actual(self):
        df = self.wa.decision_frame("09:00")
        row = df[df["startTime"] == pd.Timestamp("2026-01-03 00:00", tz="UTC")].iloc[0]
        self.assertAlmostEqual(row["error_mw"], 100 + 10 * 15, places=6)  # known by construction

    def test_forecast_error_matches_construction_in_accuracy(self):
        acc = self.wa.accuracy("09:00")
        # errors range 250..485 MW, all positive -> bias == mae, over-forecast 100%
        self.assertAlmostEqual(acc["overall"]["bias_mw"], acc["overall"]["mae_mw"], places=1)
        self.assertEqual(acc["overall"]["over_forecast_share_pct"], 100.0)
        self.assertEqual(acc["overall"]["n"], 5 * 48)

    def test_band_has_no_lookahead(self):
        v = self.wa.decision_view(date(2026, 1, 5), "09:00")
        # history = delivery days 2, 3, 4 Jan only
        self.assertEqual(v["band"]["history_days"], 3)
        self.assertFalse(v["band"]["in_sample"])

    def test_first_day_flags_in_sample(self):
        v = self.wa.decision_view(date(2026, 1, 2), "09:00")
        self.assertTrue(v["band"]["in_sample"])

    def test_earlier_forecast_and_revision(self):
        v = self.wa.decision_view(date(2026, 1, 3), "09:00", compare_hours=6)
        s = v["summary"]
        # earlier forecast has horizon +6h -> 60 MW higher error -> revision is -60 MW
        self.assertAlmostEqual(s["revision_mean_mw"], -60.0, places=0)

    def test_payload_is_json_safe(self):
        for fn in (lambda: self.wa.decision_view(date(2026, 1, 2), "09:00"),
                   lambda: self.wa.decision_view(date(2026, 1, 20), "09:00"),  # no data at all
                   lambda: self.wa.accuracy("09:00"),
                   lambda: self.wa.horizon()):
            json.dumps(fn(), allow_nan=False)

    def test_horizon_error_grows_with_lead_time(self):
        h = self.wa.horizon(bin_hours=6)["bins"]
        maes = [b["mae_mw"] for b in h]
        self.assertEqual(maes, sorted(maes))
        self.assertGreater(maes[-1], maes[0])

    def test_baseline_present(self):
        self.assertIsNotNone(self.wa.accuracy("09:00")["baseline"])


class TestHourlyForecasts(unittest.TestCase):
    """Real WINDFOR data is hourly while FUELHH actuals are half-hourly."""

    @classmethod
    def setUpClass(cls):
        cls.wa = synthetic(hourly=True)

    def test_metrics_use_only_real_forecast_points(self):
        acc = self.wa.accuracy("09:00")
        self.assertEqual(acc["overall"]["n"], 5 * 24)        # not 5 * 48

    def test_display_series_is_full_half_hourly_with_no_gaps(self):
        v = self.wa.decision_view(date(2026, 1, 3), "09:00")
        self.assertEqual(len(v["series"]), 48)
        self.assertTrue(all(r["forecast_mw"] is not None for r in v["series"]))
        self.assertEqual(v["summary"]["periods"], 48)

    def test_interpolated_points_are_flagged_and_have_no_error(self):
        df = self.wa.decision_frame("09:00")
        half = df[df["startTime"].dt.minute == 30]
        self.assertFalse(half["native"].any())
        self.assertTrue(half["error_mw"].isna().all())

    def test_horizon_range_counts_only_real_points(self):
        v = self.wa.decision_view(date(2026, 1, 3), "09:00")
        self.assertEqual(v["summary"]["horizon_min_h"], 15.0)
        self.assertEqual(v["summary"]["horizon_max_h"], 38.0)  # last real point is 23:00

    def test_energy_uses_half_hour_weights_on_filled_series(self):
        v = self.wa.decision_view(date(2026, 1, 3), "09:00")
        approx = v["summary"]["mean_mw"] * 24 / 1000          # MW * 24 h -> GWh
        self.assertAlmostEqual(v["summary"]["energy_gwh"], approx, delta=0.5)

    def test_json_safe(self):
        json.dumps(self.wa.decision_view(date(2026, 1, 4), "09:00"), allow_nan=False)
        json.dumps(self.wa.accuracy("09:00"), allow_nan=False)


if __name__ == "__main__":
    unittest.main()
