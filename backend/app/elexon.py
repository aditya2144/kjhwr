"""Thin client for the Elexon BMRS (Insights) open API. No API key is needed."""
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests

from .config import ELEXON_BASE

HEADERS = {"Accept": "application/json", "User-Agent": "wind-forecast-challenge/1.0"}


def _get(path: str, params: dict, retries: int = 5, timeout: int = 90) -> list[dict]:
    """GET with retry/back-off for 429 and 5xx. Returns the list of records."""
    url = f"{ELEXON_BASE}{path}"
    last: Exception | None = None
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
            r.raise_for_status()
            body = r.json()
            return body["data"] if isinstance(body, dict) and "data" in body else body
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status is not None and 400 <= status < 500 and status != 429:
                raise                      # a real client error: do not retry
            last = exc
        except (requests.RequestException, ValueError) as exc:
            last = exc
        time.sleep(2 ** attempt)
    raise RuntimeError(f"Elexon request failed after {retries} attempts: {url} {params}: {last}")


def _chunks(start: date, end: date, days: int):
    cur = start
    while cur <= end:
        nxt = min(cur + timedelta(days=days - 1), end)
        yield cur, nxt
        cur = nxt + timedelta(days=1)


def fetch_actuals(start: date, end: date) -> pd.DataFrame:
    """FUELHH half-hourly wind generation (MW) by settlement date. -> [startTime, generation]"""
    rows: list[dict] = []
    for a, b in _chunks(start, end, 7):
        params = {"settlementDateFrom": a.isoformat(), "settlementDateTo": b.isoformat(), "fuelType": "WIND"}
        try:
            part = _get("/datasets/FUELHH/stream", params)
        except requests.HTTPError:          # server rejected the fuelType filter: filter client-side
            params.pop("fuelType")
            part = _get("/datasets/FUELHH/stream", params)
        rows += [r for r in part if r.get("fuelType", "WIND") == "WIND"]
        print(f"  FUELHH {a}..{b}: {len(part)} rows")
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No FUELHH rows returned")
    df = df[["startTime", "generation"]].copy()
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"])
    return df.drop_duplicates("startTime", keep="last").sort_values("startTime").reset_index(drop=True)


def fetch_forecasts(publish_from: date, publish_to: date) -> pd.DataFrame:
    """WINDFOR forecasts by publish time. -> [startTime, publishTime, generation]"""
    rows: list[dict] = []
    for a, b in _chunks(publish_from, publish_to, 2):
        frm = datetime(a.year, a.month, a.day, tzinfo=timezone.utc)
        to = datetime(b.year, b.month, b.day, tzinfo=timezone.utc) + timedelta(days=1)
        params = {"publishDateTimeFrom": frm.strftime("%Y-%m-%dT%H:%MZ"),
                  "publishDateTimeTo": to.strftime("%Y-%m-%dT%H:%MZ")}
        part = _get("/datasets/WINDFOR/stream", params)
        rows += part
        print(f"  WINDFOR published {a}..{b}: {len(part)} rows")
    df = pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError("No WINDFOR rows returned")
    df = df[["startTime", "publishTime", "generation"]].copy()
    df["startTime"] = pd.to_datetime(df["startTime"], utc=True)
    df["publishTime"] = pd.to_datetime(df["publishTime"], utc=True)
    df["generation"] = pd.to_numeric(df["generation"])
    return (df.drop_duplicates(["startTime", "publishTime"], keep="last")
              .sort_values(["publishTime", "startTime"]).reset_index(drop=True))
