"""Service layer: runs the SQL in queries.py and assembles API-ready results."""
from __future__ import annotations

import math
import random

from . import queries as q
from .db import get_db

PRESETS = {
    "Base case": {"haircut_shock": 0.0, "delay_days": 0, "margin_mult": 1.0},
    "Moderate stress": {"haircut_shock": 0.05, "delay_days": 1, "margin_mult": 1.10},
    "Severe stress": {"haircut_shock": 0.10, "delay_days": 2, "margin_mult": 1.20},
}


def _p(haircut_shock: float, delay_days: int, margin_mult: float) -> dict:
    return {
        "haircut_shock": repr(float(haircut_shock)),
        "delay_days": int(delay_days),
        "margin_mult": repr(float(margin_mult)),
    }


def eligible_collateral(haircut_shock=0.0):
    p = _p(haircut_shock, 0, 1.0)
    return get_db().query(q.ELIGIBLE_SQL.format(**p))


def ladder(haircut_shock=0.0, delay_days=0, margin_mult=1.0):
    p = _p(haircut_shock, delay_days, margin_mult)
    return get_db().query(q.LADDER_SQL.format(**p))


def metrics(haircut_shock=0.0, delay_days=0, margin_mult=1.0) -> dict:
    p = _p(haircut_shock, delay_days, margin_mult)
    r = get_db().query(q.METRICS_SQL.format(**p)).iloc[0]
    first = None if r["first_shortfall_day"] is None or _isnan(r["first_shortfall_day"]) else int(r["first_shortfall_day"])
    return {
        "min_buffer": float(r["min_buffer"]),
        "peak_shortfall": float(r["peak_shortfall"]),
        "first_shortfall_day": first,
        "shortfall_days": int(r["shortfall_days"]),
        "last_day": int(r["last_day"]),
    }


def funding(haircut_shock=0.0, delay_days=0, margin_mult=1.0) -> dict:
    m = metrics(haircut_shock, delay_days, margin_mult)
    if m["first_shortfall_day"] is None:
        return {"metrics": m, "waterfall": [], "single": [], "total_cost": 0.0, "residual_gap": 0.0}
    fp = {
        "first_day": m["first_shortfall_day"],
        "shortfall": repr(m["peak_shortfall"]),
        "days_out": m["last_day"] - m["first_shortfall_day"] + 1,
    }
    db = get_db()
    wf = db.query(q.FUNDING_SQL.format(**fp))
    single = db.query(q.SINGLE_ACTION_SQL.format(**fp))
    drawn = float(wf["draw_amount"].sum())
    return {
        "metrics": m,
        "waterfall": wf.to_dict("records"),
        "single": single.to_dict("records"),
        "total_cost": float(wf["intervention_cost"].sum()),
        "residual_gap": max(0.0, m["peak_shortfall"] - drawn),
    }


def counterparty_exposure():
    return get_db().query(q.EXPOSURE_SQL)


# ---- Monte Carlo ---------------------------------------------------------------
def mc_eligible_p5(amount, haircut, vol, n_paths, seed):
    """Python twin of the Exasol UDF MC_ELIGIBLE_P5 (sql/04_udf_monte_carlo.sql). Keep in sync."""
    rnd = random.Random(int(seed))
    vals = sorted(float(amount) * (1.0 - min(1.0, float(haircut) + abs(rnd.gauss(0.0, float(vol)))))
                  for _ in range(int(n_paths)))
    return vals[int(0.05 * int(n_paths))]


def monte_carlo(vol=0.05, n_paths=2000, seed=42) -> dict:
    db = get_db()
    vol, n_paths, seed = float(vol), int(n_paths), int(seed)
    if db.backend == "exasol":
        df = db.query(q.MC_EXASOL_SQL.format(vol=repr(vol), n_paths=n_paths, seed=seed))
        where = "in-database Exasol Python UDF"
    else:
        df = db.query(q.MC_BASE_SQL)
        df["p5_eligible"] = [mc_eligible_p5(a, h, vol, n_paths, seed)
                             for a, h in zip(df["amount"], df["haircut_pct"])]
        where = "local Python (UDF twin)"
    base, p5 = float(df["base_eligible"].sum()), float(df["p5_eligible"].sum())
    return {"executed_in": where, "base_eligible": base, "p5_eligible": p5,
            "tail_loss": base - p5, "assets": df[["asset_id", "asset_type", "base_eligible", "p5_eligible"]].to_dict("records")}


def _isnan(v) -> bool:
    try:
        return math.isnan(float(v))
    except (TypeError, ValueError):
        return v is None
