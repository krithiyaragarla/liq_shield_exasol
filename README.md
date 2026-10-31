# 🛡 LiqShield — Collateral & Liquidity Stress Intelligence Core

**Exasol Exathon · Track B: Money, risk and financial derivatives**

> *Will we survive Friday's margin calls?*  LiqShield answers whether a financial institution can meet
> time-sensitive cash obligations with the cash and collateral it can **actually mobilise** — after haircuts,
> encumbrances and settlement lags — and what it costs to fix a shortfall.

## 1. Problem statement

Treasury and risk teams must know, bucket by bucket, whether margin calls, settlements and fees can be paid on time.
Headline collateral is misleading: some assets are already pledged (encumbered), every asset loses value through
haircuts, assets take time to turn into cash, and incoming cash can arrive late. A shortfall that appears on T+3 is
a very different problem from one that appears on T+7, because funding lines have lead times.

LiqShield computes, for any stress scenario:

| Requirement (track brief) | Where it is implemented |
|---|---|
| Eligible collateral after haircuts and encumbrances | `ELIGIBLE_SQL` (`app/liqshield/queries.py`) |
| Margin calls, funding deadlines, settlement delays | scenario knobs in `LADDER_CTES` (haircut shock, inflow delay, margin multiplier) |
| Compare funding actions under liquidity & facility constraints | `FUNDING_SQL` (cheapest-first waterfall with lead-time feasibility), `SINGLE_ACTION_SQL` |
| Shortfall severity, time to shortfall, intervention cost | `METRICS_SQL` + `FUNDING_SQL` |
| Hand-calculable validation | `validation/LiqShield_Validation.xlsx` + `tests/test_engine.py` |

## 2. Exasol's role

All financial logic runs **inside the database**: joins (collateral × haircut rules), eligibility filters, time-bucket
aggregation, window-function cumulative ladders (`SUM() OVER (ORDER BY day)`), funding waterfall with a running
window sum, and an **in-database Python UDF** (`MC_ELIGIBLE_P5`, `sql/04_udf_monte_carlo.sql`) for Monte Carlo
haircut-shock simulation. Python/FastAPI only parameterises and serialises; Streamlit only draws.

```
Streamlit dashboard ──▶ FastAPI (app/api.py) ──▶ engine.py ──▶ queries.py (SQL) ──▶ Exasol Personal
                                                                                    └─ (fallback) DuckDB, same SQL
```

## 3. Quick start

### A. Run on Exasol Personal (submission mode)

1. Install the launcher and a database (see <https://docs.exasol.com/db/latest/get_started/quick_start_guide.htm>):
   ```bash
   curl https://www.exasol.com/install/ | sh      # installs the `exasol` launcher
   mkdir deployment && cd deployment
   exasol install local      # macOS 15+ on Apple silicon, 8 GB RAM   (or: exasol install aws | azure)
   exasol info               # prints host, port, user, password
   ```
2. Install the project and point it at the database:
   ```bash
   git clone <this repo> && cd liqshield
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env      # edit EXASOL_DSN / EXASOL_PASSWORD from `exasol info`
   ```
3. Create schema, tables, data and the UDF in Exasol, then verify:
   ```bash
   python scripts/load_exasol.py
   # expect: VERIFY total eligible collateral = 22,550,000.00
   ```
   *No Python loader? Run the SQL files in order with any SQL client (DBeaver) or the launcher:*
   `exasol connect -f sql/01_schema.sql`, then `02_tables.sql`, `03_seed_data.sql`, `04_udf_monte_carlo.sql`.
4. Start the API and dashboard (two terminals):
   ```bash
   uvicorn app.api:app --port 8000      # GET / should show {"backend":"exasol"}
   streamlit run app/dashboard.py
   ```

### B. Run locally without Exasol (development / reviewer convenience)

Leave `EXASOL_DSN` empty (or don't create `.env`). The identical SQL runs on an in-memory DuckDB loaded from `data/*.csv`.
The dashboard header shows which engine is active (`EXASOL` / `DUCKDB`).

```bash
pip install -r requirements.txt
make test      # 11 tests: SQL vs independent oracle vs hand calculations
make api       # terminal 1
make ui        # terminal 2
```

## 4. Validation (proof the maths is right)

* `tests/test_engine.py` — asserts SQL output equals (a) an independent pure-Python oracle (`app/liqshield/reference.py`,
  shares no code with the SQL) and (b) hand-calculated constants, across four scenarios.
* `validation/LiqShield_Validation.xlsx` — a formula-driven Excel re-computation. Switch the scenario in `Inputs!B2`;
  `Ladder!B15` shows **PASS** when Excel matches the database output to the cent for all 8 buckets.

Hand calculation of the starting buffer (cash 5.0M; AST-003 8M encumbered → 0):

```
Cash                 5,000,000 × (1 − 0%)  =  5,000,000
US Treasury         10,000,000 × (1 − 2%)  =  9,800,000
Corp AAA (AST-006)   4,000,000 × (1 − 5%)  =  3,800,000
Corp BBB             2,000,000 × (1 − 15%) =  1,700,000
Equities             3,000,000 × (1 − 25%) =  2,250,000
                                              ----------
Total eligible                                22,550,000
```

Scenario results (synthetic data, as-of 2026-11-02):

| Scenario | Haircut | Delay | Margin × | Lowest buffer | First breach | Peak gap | Cheapest cover |
|---|---|---|---|---|---|---|---|
| Base | +0pp | 0d | 1.00 | $2.95M | none | – | – |
| Moderate | +5pp | 1d | 1.10 | −$0.27M | T+5 | $270k | $56 |
| Severe | +10pp | 2d | 1.20 | −$4.49M | T+4 | $4.49M | $1,247 (FAC-01) |

## 5. Methodology & assumptions

* **Mobilisable liquidity** on day *d* = Σ eligible value of unencumbered assets whose settlement lag ≤ *d*.
  Eligible value = market value × (1 − min(1, haircut + shock)).
* **Buffer** = mobilisable + cumulative net cashflow. Shortfall = buffer < 0.
* **Stress knobs**: additive haircut shock; inflows shifted later by *n* days (outflows are not); margin calls
  (`MARGIN_CALL`, `STRESS_MARGIN_CALL`) scaled by a multiplier.
* **Funding waterfall**: facilities not drawable by the first breach day are excluded ("too late"); the rest are drawn
  cheapest-first up to their limit until the **peak** shortfall is covered. Cost =
  draw × (annual bps/10,000 × days outstanding/360 + upfront bps/10,000). Drawing the peak amount at the first breach is a
  deliberately conservative simplification.
* Funding facilities are treated as independent of the collateral inventory (no double counting of repo collateral).
* Single currency (USD); FX, intraday timing and netting sets are out of scope for the 48-hour build.

## 6. Data sources and licence

All data is **synthetic**, hand-designed and generated by `scripts/generate_data.py` (no randomness, no real
institutions; "Bank_A/B/C" are placeholders). No external datasets are used. Data is released under **CC0 1.0**
(public domain). Haircut percentages are illustrative round numbers in the spirit of regulatory haircut schedules, not
taken from any specific rulebook. Source code is **MIT** (see `LICENSE`).

## 7. APIs and third-party tools

| Tool | Use | Licence |
|---|---|---|
| Exasol Personal | analytics database (mandatory platform) | Exasol Personal terms (free, non-commercial) |
| pyexasol | Python driver for Exasol | MIT |
| DuckDB | local fallback engine | MIT |
| FastAPI / Uvicorn | REST API | MIT / BSD-3 |
| Streamlit | dashboard | Apache-2.0 |
| Plotly | charts | MIT |
| pandas / NumPy | data handling | BSD-3 |
| openpyxl | builds the Excel validation workbook | MIT |
| pytest / httpx | tests | MIT / BSD-3 |

No external web APIs or paid services are called. AI assistance (Claude, Gemini) was used for planning and code drafting.

## 8. API reference

`GET /api/liquidity-ladder | /api/metrics | /api/funding?haircut_shock=0.10&delay_days=2&margin_mult=1.2`,
`GET /api/collateral`, `/api/exposure`, `/api/monte-carlo?vol=0.05&n_paths=2000&seed=42`, `/api/presets`.
Interactive docs at `http://127.0.0.1:8000/docs`.

## 9. Repository layout

```
sql/        01_schema (Exasol) · 02_tables · 03_seed_data · 04_udf_monte_carlo
app/        api.py · dashboard.py · liqshield/{db,queries,engine,reference}.py
scripts/    generate_data.py · load_exasol.py · build_excel.py
data/       synthetic CSVs          validation/  Excel proof          tests/  pytest
docs/       SUBMISSION.md (form text) · DEMO_SCRIPT.md (video)
```

## 10. Verification status (honest notes)

* The SQL, API, dashboard logic, tests and Excel model are verified end-to-end on the DuckDB backend (11/11 tests pass;
  Excel recalculated in LibreOffice shows PASS for all three presets).
* The Exasol-specific parts — `pyexasol` connection, `scripts/load_exasol.py`, and the Python UDF — must be run once
  against your Exasol Personal instance. If the UDF fails (script-language container differences), the dashboard's
  other views are unaffected; the Monte Carlo tab needs the UDF in Exasol mode.
