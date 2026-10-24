"""Pure-pandas analysis of wind forecasts vs actuals.

No web or I/O code lives here, so everything is unit-testable.

Conventions
-----------
* All timestamps are timezone-aware UTC internally. "Cutoff" times are given
  as London local HH:MM on the day before delivery (the day-ahead decision).
* error_mw = forecast_mw - actual_mw
    > 0  over-forecast : less wind arrived than expected -> risk of a shortfall
    < 0  under-forecast: more wind arrived than expected -> surplus
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

LONDON = ZoneInfo("Europe/London")
NS_UTC = "datetime64[ns, UTC]"


# --------------------------------------------------------------------------- helpers
def to_utc_ns(s: pd.Series) -> pd.Series:
    """Parse to tz-aware UTC with ns resolution (merge_asof needs equal dtypes)."""
    return pd.to_datetime(s, utc=True).astype(NS_UTC)


def iso(ts) -> str | None:
    if ts is None or pd.isna(ts):
        return None
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def num(x, nd: int = 1):
    """float -> rounded float, NaN/inf -> None (JSON safe)."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if (np.isnan(x) or np.isinf(x)) else round(x, nd)


def cutoff_for(delivery_date: date, cutoff_hhmm: str, lead_days: int = 1) -> pd.Timestamp:
    hh, mm = (int(p) for p in cutoff_hhmm.split(":"))
    local = datetime.combine(delivery_date - timedelta(days=lead_days), time(hh, mm), tzinfo=LONDON)
    return pd.Timestamp(local).tz_convert("UTC")


def day_bounds(d: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    """[start, end) of a London calendar day, in UTC."""
    start = pd.Timestamp(datetime.combine(d, time(0, 0), tzinfo=LONDON)).tz_convert("UTC")
    end = pd.Timestamp(datetime.combine(d + timedelta(days=1), time(0, 0), tzinfo=LONDON)).tz_convert("UTC")
    return start, end


def day_targets(d: date) -> pd.DatetimeIndex:
    start, end = day_bounds(d)
    return pd.date_range(start, end, freq="30min", inclusive="left").astype(NS_UTC)


def _fill_day(df: pd.DataFrame) -> pd.DataFrame:
    """Interpolate forecast gaps within one delivery day; remember which rows were real."""
    df = df.sort_values("startTime").copy()
    df["native"] = df["forecast_mw"].notna()
    df["forecast_mw"] = df["forecast_mw"].interpolate(limit_direction="both")
    df["publishTime"] = df["publishTime"].ffill().bfill()
    return df


# --------------------------------------------------------------------------- metrics
def compute_metrics(df: pd.DataFrame, err: str = "error_mw", actual: str = "actual_mw") -> dict:
    d = df.dropna(subset=[err, actual])
    n = len(d)
    if n == 0:
        return {"n": 0}
    e = d[err].to_numpy(dtype=float)
    a = d[actual].to_numpy(dtype=float)
    p5, p10, p50, p90, p95 = np.percentile(e, [5, 10, 50, 90, 95])
    return {
        "n": int(n),
        "mae_mw": num(np.abs(e).mean()),
        "rmse_mw": num(np.sqrt((e ** 2).mean())),
        "bias_mw": num(e.mean()),
        "wape_pct": num(np.abs(e).sum() / a.sum() * 100) if a.sum() > 0 else None,
        "mean_actual_mw": num(a.mean()),
        "p5_error_mw": num(p5),
        "p10_error_mw": num(p10),
        "median_error_mw": num(p50),
        "p90_error_mw": num(p90),
        "p95_error_mw": num(p95),          # 1-in-20 half-hours wind was at least this far below forecast
        "over_forecast_share_pct": num((e > 0).mean() * 100),
    }


def uncertainty_band(forecast: pd.Series, hist_errors: np.ndarray, lo_pct: float, hi_pct: float):
    """Turn historical signed errors into an expected-actual range around a forecast.

    actual = forecast - error, so the *high* error percentile gives the *low* actual.
    """
    q_lo, q_hi = np.percentile(hist_errors, [lo_pct, hi_pct])
    lower = (forecast - q_hi).clip(lower=0)
    upper = (forecast - q_lo).clip(lower=0)
    return lower, upper, float(q_lo), float(q_hi)


# --------------------------------------------------------------------------- core
class WindAnalysis:
    """Holds actuals + forecasts and answers the questions the UI asks.

    actuals   : columns [startTime, actual_mw]
    forecasts : columns [startTime, publishTime, forecast_mw]
    """

    def __init__(self, actuals: pd.DataFrame, forecasts: pd.DataFrame,
                 first_delivery: date, last_delivery: date,
                 band_pcts: tuple[float, float] = (5, 95)):
        a = actuals[["startTime", "actual_mw"]].copy()
        a["startTime"] = to_utc_ns(a["startTime"])
        a = a.sort_values("startTime").drop_duplicates("startTime", keep="last")
        f = forecasts[["startTime", "publishTime", "forecast_mw"]].copy()
        f["startTime"] = to_utc_ns(f["startTime"])
        f["publishTime"] = to_utc_ns(f["publishTime"])
        f = f.sort_values("publishTime").drop_duplicates(["startTime", "publishTime"], keep="last")
        self.actuals, self.forecasts = a.reset_index(drop=True), f.reset_index(drop=True)
        self.first_delivery, self.last_delivery = first_delivery, last_delivery
        self.band_pcts = band_pcts
        self._frames: dict[str, pd.DataFrame] = {}

    # ---- the forecast a trader actually had in hand ------------------------------
    def _latest_before(self, delivery_dates: list[date], cutoff_hhmm: str, shift_hours: float = 0.0) -> pd.DataFrame:
        """For every half-hour of every delivery date, pick the most recent forecast
        published at or before (cutoff - shift_hours). Returns one row per half-hour."""
        parts = []
        for d in delivery_dates:
            t = day_targets(d)
            parts.append(pd.DataFrame({
                "startTime": t,
                "delivery_date": d,
                "cutoff": cutoff_for(d, cutoff_hhmm) - pd.Timedelta(hours=shift_hours),
            }))
        targets = pd.concat(parts, ignore_index=True)
        targets["startTime"] = targets["startTime"].astype(NS_UTC)
        targets["cutoff"] = targets["cutoff"].astype(NS_UTC)
        targets = targets.sort_values("cutoff")
        merged = pd.merge_asof(
            targets, self.forecasts.sort_values("publishTime"),
            left_on="cutoff", right_on="publishTime", by="startTime", direction="backward",
        )
        merged = merged.merge(self.actuals, on="startTime", how="left")
        # WINDFOR is HOURLY while FUELHH actuals are half-hourly. Half-hours with no forecast
        # are filled by linear interpolation for display and daily totals only; they are
        # flagged native=False and excluded from every accuracy metric.
        merged = pd.concat([_fill_day(g) for _, g in merged.groupby("delivery_date", sort=True)],
                           ignore_index=True)
        merged["horizon_h"] = (merged["startTime"] - merged["publishTime"]).dt.total_seconds() / 3600
        merged["error_mw"] = (merged["forecast_mw"] - merged["actual_mw"]).where(merged["native"])
        return merged.sort_values("startTime").reset_index(drop=True)

    def _all_delivery_dates(self) -> list[date]:
        n = (self.last_delivery - self.first_delivery).days + 1
        return [self.first_delivery + timedelta(days=i) for i in range(n)]

    def decision_frame(self, cutoff: str) -> pd.DataFrame:
        if cutoff not in self._frames:
            df = self._latest_before(self._all_delivery_dates(), cutoff)
            # naive baseline: actual from the same half-hour two days earlier
            # (always known by a day-ahead cutoff)
            base = self.actuals.rename(columns={"startTime": "t48", "actual_mw": "baseline_mw"})
            df["t48"] = (df["startTime"] - pd.Timedelta(hours=48)).astype(NS_UTC)
            df = df.merge(base, on="t48", how="left").drop(columns="t48")
            df["baseline_error_mw"] = df["baseline_mw"] - df["actual_mw"]
            self._frames[cutoff] = df
        return self._frames[cutoff]

    # ---- 1. what is the latest forecast when I need to decide? -------------------
    def decision_view(self, delivery_date: date, cutoff: str, compare_hours: float = 6.0) -> dict:
        cur = self._latest_before([delivery_date], cutoff)
        prev = self._latest_before([delivery_date], cutoff, shift_hours=compare_hours)
        df = cur.copy()
        df["earlier_forecast_mw"] = prev["forecast_mw"].to_numpy()

        # Error history strictly *before* this delivery day (no look-ahead).
        full = self.decision_frame(cutoff)
        hist = full[full["delivery_date"] < delivery_date].dropna(subset=["error_mw"])
        in_sample = hist["delivery_date"].nunique() < 2
        if in_sample:  # first days of the window: fall back to the whole month, and say so
            hist = full.dropna(subset=["error_mw"])
        has_band = len(hist) > 0 and df["forecast_mw"].notna().any()
        if has_band:
            lower, upper, q_lo, q_hi = uncertainty_band(
                df["forecast_mw"], hist["error_mw"].to_numpy(), *self.band_pcts)
            df["lower_mw"], df["upper_mw"] = lower, upper
        else:
            df["lower_mw"] = df["upper_mw"] = np.nan
            q_lo = q_hi = np.nan

        f = df["forecast_mw"]
        series = [{
            "t": iso(r.startTime),
            "forecast_mw": num(r.forecast_mw, 0),
            "actual_mw": num(r.actual_mw, 0),
            "earlier_forecast_mw": num(r.earlier_forecast_mw, 0),
            "lower_mw": num(r.lower_mw, 0),
            "upper_mw": num(r.upper_mw, 0),
            "published": iso(r.publishTime),
            "horizon_h": num(r.horizon_h, 1),
        } for r in df.itertuples()]

        summary = {"periods": int(f.notna().sum())}
        if f.notna().any():
            roll = f.rolling(6).mean()  # six half-hours = 3 hours
            wi = roll.idxmin() if roll.notna().any() else None
            imin, imax = f.idxmin(), f.idxmax()
            diff = (df["forecast_mw"] - df["earlier_forecast_mw"]).dropna()
            summary.update({
                "mean_mw": num(f.mean(), 0),
                "energy_gwh": num(f.sum() * 0.5 / 1000, 1),
                "min_mw": num(f[imin], 0), "min_at": iso(df.loc[imin, "startTime"]),
                "max_mw": num(f[imax], 0), "max_at": iso(df.loc[imax, "startTime"]),
                "weakest_3h_mean_mw": num(roll[wi], 0) if wi is not None else None,
                "weakest_3h_start": iso(df.loc[wi - 5, "startTime"]) if wi is not None else None,
                "horizon_min_h": num(df.loc[df["native"], "horizon_h"].min(), 1),
                "horizon_max_h": num(df.loc[df["native"], "horizon_h"].max(), 1),
                "last_publish": iso(df["publishTime"].max()),
                "first_publish": iso(df["publishTime"].min()),
                "revision_hours": compare_hours,
                "revision_mean_mw": num(diff.mean(), 0) if len(diff) else None,
                "revision_energy_gwh": num(diff.sum() * 0.5 / 1000, 2) if len(diff) else None,
            })

        return {
            "delivery_date": delivery_date.isoformat(),
            "cutoff_local": cutoff,
            "cutoff_utc": iso(cutoff_for(delivery_date, cutoff)),
            "series": series,
            "summary": summary,
            "band": {
                "low_pct": self.band_pcts[0], "high_pct": self.band_pcts[1],
                "q_low_mw": num(q_lo, 0), "q_high_mw": num(q_hi, 0),
                "history_days": int(hist["delivery_date"].nunique()) if len(hist) else 0,
                "in_sample": bool(in_sample),
            },
            "realised": compute_metrics(df) if df["actual_mw"].notna().any() else {"n": 0},
        }

    # ---- 2. how accurate is it? ----------------------------------------------------
    def accuracy(self, cutoff: str) -> dict:
        df = self.decision_frame(cutoff)
        ok = df.dropna(subset=["error_mw"]).copy()
        overall = compute_metrics(ok)

        daily = []
        for d, g in ok.groupby("delivery_date"):
            m = compute_metrics(g)
            daily.append({"date": d.isoformat(), "mae_mw": m["mae_mw"], "bias_mw": m["bias_mw"],
                          "rmse_mw": m["rmse_mw"], "mean_actual_mw": m["mean_actual_mw"],
                          "mean_forecast_mw": num(g["forecast_mw"].mean(), 0)})

        ok["hour"] = ok["startTime"].dt.tz_convert(LONDON).dt.hour
        by_hour = [{"hour": int(h), "mae_mw": num(g["error_mw"].abs().mean(), 0),
                    "bias_mw": num(g["error_mw"].mean(), 0)} for h, g in ok.groupby("hour")]

        # error histogram (500 MW bins)
        e = ok["error_mw"].to_numpy()
        hist = []
        if len(e):
            lim = float(np.ceil(np.abs(e).max() / 500.0) * 500.0) or 500.0
            edges = np.arange(-lim, lim + 500.0, 500.0)
            counts, edges = np.histogram(e, bins=edges)
            hist = [{"from_mw": int(edges[i]), "to_mw": int(edges[i + 1]), "count": int(c)}
                    for i, c in enumerate(counts)]

        base = ok.dropna(subset=["baseline_error_mw"])
        baseline = None
        if len(base):
            mae_f = base["error_mw"].abs().mean()
            mae_b = base["baseline_error_mw"].abs().mean()
            baseline = {"description": "actual wind from the same half-hour two days earlier",
                        "mae_mw": num(mae_b), "forecast_mae_mw": num(mae_f),
                        "improvement_pct": num((1 - mae_f / mae_b) * 100) if mae_b > 0 else None}
        return {"cutoff_local": cutoff, "overall": overall, "daily": daily, "by_hour": by_hour,
                "histogram": hist, "baseline": baseline,
                "decision_horizon_h": {"min": num(ok["horizon_h"].min()), "max": num(ok["horizon_h"].max())}}

    # ---- 3. does accuracy improve closer to delivery? --------------------------------
    def horizon(self, bin_hours: int = 3) -> dict:
        start, _ = day_bounds(self.first_delivery)
        _, end = day_bounds(self.last_delivery)
        f = self.forecasts[(self.forecasts["startTime"] >= start) & (self.forecasts["startTime"] < end)]
        j = f.merge(self.actuals, on="startTime", how="inner")
        j["horizon_h"] = (j["startTime"] - j["publishTime"]).dt.total_seconds() / 3600
        j = j[j["horizon_h"] >= 0].copy()
        j["error_mw"] = j["forecast_mw"] - j["actual_mw"]
        j["bin"] = (np.floor(j["horizon_h"] / bin_hours) * bin_hours).astype(int)
        rows = []
        for b, g in j.groupby("bin"):
            m = compute_metrics(g)
            rows.append({"from_h": int(b), "to_h": int(b + bin_hours), "n": m["n"], "mae_mw": m["mae_mw"],
                         "rmse_mw": m["rmse_mw"], "bias_mw": m["bias_mw"], "wape_pct": m["wape_pct"]})
        return {"bin_hours": bin_hours, "bins": rows}

    def meta(self, default_cutoff: str, cutoff_options: list[str]) -> dict:
        return {
            "first_delivery": self.first_delivery.isoformat(),
            "last_delivery": self.last_delivery.isoformat(),
            "default_cutoff": default_cutoff,
            "cutoff_options": cutoff_options,
            "band": {"low_pct": self.band_pcts[0], "high_pct": self.band_pcts[1]},
            "actual_rows": int(len(self.actuals)),
            "forecast_rows": int(len(self.forecasts)),
        }
