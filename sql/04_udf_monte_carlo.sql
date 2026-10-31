-- Exasol only. Python UDF that runs INSIDE the database.
-- Simulates n_paths random haircut shocks (|N(0, vol)| added to the base haircut, capped at 100%)
-- and returns the 5th-percentile (worst-case) eligible value of one asset.
-- Pure-Python (no numpy) so it works in the stock Python3 script language container.
-- The identical algorithm lives in app/liqshield/engine.py::mc_eligible_p5 for local (DuckDB) mode.
OPEN SCHEMA LIQSHIELD;

CREATE OR REPLACE PYTHON3 SCALAR SCRIPT MC_ELIGIBLE_P5
    (amount DOUBLE, haircut DOUBLE, vol DOUBLE, n_paths DOUBLE, seed DOUBLE)
RETURNS DOUBLE AS
import random

def run(ctx):
    if ctx.amount is None:
        return None
    n = int(ctx.n_paths)
    rnd = random.Random(int(ctx.seed))
    vals = []
    for _ in range(n):
        shock = abs(rnd.gauss(0.0, ctx.vol))
        hc = min(1.0, ctx.haircut + shock)
        vals.append(ctx.amount * (1.0 - hc))
    vals.sort()
    return vals[int(0.05 * n)]
/

-- Smoke test:
-- SELECT SUM(MC_ELIGIBLE_P5(c.AMOUNT, h.HAIRCUT_PCT, 0.05, 2000, 42)) FROM COLLATERAL_INVENTORY c
--   JOIN HAIRCUT_RULES h ON c.ASSET_TYPE = h.ASSET_TYPE WHERE c.ENCUMBERED_FLAG = FALSE;
