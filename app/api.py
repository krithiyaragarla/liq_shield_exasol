"""LiqShield FastAPI service.  Run:  uvicorn app.api:app --reload   (from repo root)"""
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from app.liqshield import engine
from app.liqshield.db import get_db

app = FastAPI(title="LiqShield API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

Haircut = Query(0.0, ge=0.0, le=0.6, description="Additive haircut shock, 0.10 = +10pp")
Delay = Query(0, ge=0, le=5, description="Days incoming cash is delayed")
Margin = Query(1.0, ge=0.5, le=3.0, description="Margin call multiplier")


def _records(df):
    df = df.copy()
    for c in df.columns:
        if "date" in c:
            df[c] = df[c].astype(str)
    return df.to_dict("records")


@app.get("/")
def health():
    return {"status": "ok", "backend": get_db().backend}


@app.get("/api/presets")
def presets():
    return engine.PRESETS


@app.get("/api/collateral")
def collateral(haircut_shock: float = Haircut):
    return _records(engine.eligible_collateral(haircut_shock))


@app.get("/api/liquidity-ladder")
def liquidity_ladder(haircut_shock: float = Haircut, delay_days: int = Delay, margin_mult: float = Margin):
    return _records(engine.ladder(haircut_shock, delay_days, margin_mult))


@app.get("/api/metrics")
def metrics(haircut_shock: float = Haircut, delay_days: int = Delay, margin_mult: float = Margin):
    return engine.metrics(haircut_shock, delay_days, margin_mult)


@app.get("/api/funding")
def funding(haircut_shock: float = Haircut, delay_days: int = Delay, margin_mult: float = Margin):
    return engine.funding(haircut_shock, delay_days, margin_mult)


@app.get("/api/exposure")
def exposure():
    return _records(engine.counterparty_exposure())


@app.get("/api/monte-carlo")
def monte_carlo(vol: float = Query(0.05, gt=0, le=0.5), n_paths: int = Query(2000, ge=100, le=20000),
                seed: int = 42):
    return engine.monte_carlo(vol, n_paths, seed)
