"""Create the LIQSHIELD schema, tables, seed data and the Monte Carlo UDF in Exasol, then verify.

Usage (env vars from .env.example):
    python scripts/load_exasol.py

Works against Exasol Personal (local macOS or cloud) because it only needs a websocket connection (port 8563).
"""
import os
import re
import ssl
from pathlib import Path

import pyexasol

ROOT = Path(__file__).resolve().parent.parent
SQL = ROOT / "sql"


def statements(text: str):
    text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("--"))
    return [s.strip() for s in text.split(";") if s.strip()]


def main() -> None:
    dsn = os.environ["EXASOL_DSN"]
    conn = pyexasol.connect(
        dsn=dsn,
        user=os.getenv("EXASOL_USER", "sys"),
        password=os.environ["EXASOL_PASSWORD"],
        encryption=True,
        websocket_sslopt={"cert_reqs": ssl.CERT_NONE},  # Exasol Personal ships a self-signed certificate
    )
    print("connected to", dsn)

    for f in ["01_schema.sql", "02_tables.sql", "03_seed_data.sql"]:
        for s in statements((SQL / f).read_text()):
            if s.upper() == "COMMIT":
                continue
            conn.execute(s)
        print("ran", f)

    # The UDF body contains semicolons/newlines, so it is executed as one statement (terminated by '/').
    udf = (SQL / "04_udf_monte_carlo.sql").read_text()
    m = re.search(r"(CREATE OR REPLACE PYTHON3.*?)^/\s*$", udf, re.S | re.M)
    conn.execute(m.group(1).strip())
    print("created UDF MC_ELIGIBLE_P5")

    total = conn.execute("""SELECT SUM(c.AMOUNT * (1 - h.HAIRCUT_PCT)) FROM COLLATERAL_INVENTORY c
                            JOIN HAIRCUT_RULES h ON c.ASSET_TYPE = h.ASSET_TYPE
                            WHERE c.ENCUMBERED_FLAG = FALSE""").fetchval()
    print(f"VERIFY total eligible collateral = {float(total):,.2f}  (expected 22,550,000.00)")
    p5 = conn.execute("""SELECT SUM(MC_ELIGIBLE_P5(c.AMOUNT, h.HAIRCUT_PCT, 0.05, 2000, 42))
                         FROM COLLATERAL_INVENTORY c JOIN HAIRCUT_RULES h ON c.ASSET_TYPE = h.ASSET_TYPE
                         WHERE c.ENCUMBERED_FLAG = FALSE""").fetchval()
    print(f"VERIFY UDF p5 eligible = {float(p5):,.2f}")
    conn.close()


if __name__ == "__main__":
    main()
