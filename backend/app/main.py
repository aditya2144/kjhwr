"""FastAPI application: a thin, read-only JSON layer over `analysis.WindAnalysis`."""
from datetime import date, timedelta
from functools import lru_cache

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .analysis import WindAnalysis
from .store import load_analysis

app = FastAPI(
    title="Day-ahead wind forecast decision support",
    description="National GB wind generation: forecast available at the day-ahead decision "
                "time, and how accurate that forecast has been. Data: Elexon BMRS (FUELHH, WINDFOR).",
    version="1.0.0",
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"])


@lru_cache(maxsize=1)
def _analysis() -> WindAnalysis:
    return load_analysis()


def wa() -> WindAnalysis:
    try:
        return _analysis()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def check_cutoff(cutoff: str) -> str:
    if cutoff not in config.CUTOFF_OPTIONS:
        raise HTTPException(status_code=422, detail=f"cutoff must be one of {config.CUTOFF_OPTIONS}")
    return cutoff


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/meta")
def meta():
    return wa().meta(config.DEFAULT_CUTOFF, config.CUTOFF_OPTIONS)


@app.get("/api/decision")
def decision(delivery_date: date = Query(..., description="Delivery day (the day being bought for)"),
             cutoff: str = Query(config.DEFAULT_CUTOFF, description="Decision time, London HH:MM, day before delivery")):
    check_cutoff(cutoff)
    if not (config.FIRST_DELIVERY <= delivery_date <= config.LAST_DELIVERY):
        raise HTTPException(status_code=422, detail=(
            f"delivery_date must be between {config.FIRST_DELIVERY} and {config.LAST_DELIVERY} "
            "(decisions made in January 2026)"))
    return wa().decision_view(delivery_date, cutoff)


@app.get("/api/accuracy")
def accuracy(cutoff: str = Query(config.DEFAULT_CUTOFF)):
    check_cutoff(cutoff)
    return wa().accuracy(cutoff)


@app.get("/api/horizon")
def horizon(bin_hours: int = Query(3, ge=1, le=12)):
    return wa().horizon(bin_hours)
