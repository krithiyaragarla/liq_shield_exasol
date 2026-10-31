"""Database access. One interface, two backends:

* Exasol (pyexasol)  - used when EXASOL_DSN is set.  This is the primary / submission backend.
* DuckDB (in-memory) - fallback for developing without an Exasol connection. Same schema, same SQL.
"""
from __future__ import annotations

import os
import re
import ssl
from decimal import Decimal
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

# Minimal .env loader (no extra dependency): KEY=VALUE lines, existing env vars win.
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text().splitlines():
        if "=" in _line and not _line.strip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [str(c).lower() for c in df.columns]
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = df[c].map(lambda v: float(v) if isinstance(v, Decimal) else v)
    return df


class Database:
    def __init__(self) -> None:
        self.dsn = os.getenv("EXASOL_DSN", "").strip()
        self.backend = "exasol" if self.dsn else "duckdb"
        self._duck = None
        if self.backend == "duckdb":
            self._init_duckdb()

    # ---- DuckDB (local fallback) -------------------------------------------------
    def _init_duckdb(self) -> None:
        import duckdb

        con = duckdb.connect(":memory:")
        ddl = (ROOT / "sql" / "02_tables.sql").read_text()
        for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
            con.execute(stmt)
        for name in ["haircut_rules", "collateral_inventory", "portfolio_positions",
                     "cashflow_obligations", "funding_facilities", "time_buckets"]:
            df = pd.read_csv(ROOT / "data" / f"{name}.csv")
            df.columns = [c.upper() for c in df.columns]
            con.register("_tmp", df)
            con.execute(f"INSERT INTO {name.upper()} SELECT * FROM _tmp")
            con.unregister("_tmp")
        self._duck = con

    # ---- Exasol ------------------------------------------------------------------
    def _exasol_connect(self):
        import pyexasol

        return pyexasol.connect(
            dsn=self.dsn,
            user=os.getenv("EXASOL_USER", "sys"),
            password=os.getenv("EXASOL_PASSWORD", ""),
            schema=os.getenv("EXASOL_SCHEMA", "LIQSHIELD"),
            encryption=True,
            # Exasol Personal uses a self-signed certificate by default.
            websocket_sslopt={"cert_reqs": ssl.CERT_NONE},
            fetch_dict=False,
        )

    # ---- Public API --------------------------------------------------------------
    def query(self, sql: str) -> pd.DataFrame:
        if self.backend == "duckdb":
            return _clean(self._duck.execute(sql).fetchdf())
        conn = self._exasol_connect()
        try:
            stmt = conn.execute(sql)
            cols = list(stmt.columns().keys())
            return _clean(pd.DataFrame(stmt.fetchall(), columns=cols))
        finally:
            conn.close()


_db: Database | None = None


def get_db() -> Database:
    global _db
    if _db is None:
        _db = Database()
    return _db
