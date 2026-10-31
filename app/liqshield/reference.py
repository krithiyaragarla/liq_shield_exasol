"""Independent pure-Python reference implementation (the 'oracle').

It deliberately shares no code with the SQL. Tests assert SQL == oracle == hand-calculated numbers,
which is how we prove the Exasol math is right.
"""
from __future__ import annotations

import pandas as pd

from .db import ROOT


def _load(name):
    return pd.read_csv(ROOT / "data" / f"{name}.csv")


def ladder(haircut_shock=0.0, delay_days=0, margin_mult=1.0) -> pd.DataFrame:
    inv, hc = _load("collateral_inventory"), _load("haircut_rules")
    cf, tb = _load("cashflow_obligations"), _load("time_buckets")
    rows = []
    for _, d in tb.iterrows():
        day = int(d.day_offset)
        mob = 0.0
        for _, a in inv.iterrows():
            if a.encumbered_flag or int(a.settlement_lag_days) > day:
                continue
            h = float(hc.loc[hc.asset_type == a.asset_type, "haircut_pct"].iloc[0])
            mob += a.amount * (1 - min(1.0, h + haircut_shock))
        rows.append((day, mob))
    net = {int(d): 0.0 for d in tb.day_offset}
    for _, r in cf.iterrows():
        if r.direction == "In":
            eff, amt = int(r.value_day) + delay_days, r.amount
        else:
            eff = int(r.value_day)
            amt = -r.amount * (margin_mult if r.obligation_type in ("MARGIN_CALL", "STRESS_MARGIN_CALL") else 1.0)
        if eff in net:
            net[eff] += amt
    out, cum = [], 0.0
    for day, mob in rows:
        cum += net[day]
        out.append({"day_offset": day, "net_cashflow": net[day], "cum_cashflow": cum,
                    "mobilisable": mob, "liquidity_buffer": mob + cum})
    return pd.DataFrame(out)
