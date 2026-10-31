# Demo video script (target 3 minutes)

Record the screen with the dashboard on the left and the Excel validation workbook on the right.

**0:00 – Hook (15s)** "We built LiqShield to answer one question: will we survive Friday's margin calls?"

**0:15 – Problem (20s)** Headline collateral overstates liquidity: encumbered assets, haircuts, settlement lags,
delayed inflows. Funding lines have lead times — *when* the shortfall hits matters.

**0:35 – Base case (25s)** Preset "Base case": green. Show the ladder and the Day-3 $15M Bank_B margin call dipping
the buffer to $7.85M but never below zero. Open the *Eligible collateral* tab: AST-003 is encumbered → $0; total $22.55M.

**1:00 – Stress (45s)** Switch to "Severe stress" (+10pp haircuts, inflows 2 days late, margin calls ×1.2). Banner turns
red: first breach T+4, peak gap $4.49M. Open *Funding actions*: FAC-05 parent support is flagged TOO LATE; the cheapest
in-time line (FAC-01) covers the gap for about $1.2k. Mention shortfall severity, time to shortfall, intervention cost.

**1:45 – Exasol (30s)** Say: every slider is a parameterised SQL query running in Exasol — joins, window-function
cumulative ladder, funding waterfall. Show the header "Analytics engine: EXASOL". Open *Monte Carlo* tab: executed in the
in-database Python UDF.

**2:15 – Proof (30s)** In Excel, `Ladder!B15` shows PASS. Change `Inputs!B2` to 2, then 1: still PASS. "Excel
recomputes the same numbers from first principles; our pytest suite checks SQL against an independent oracle."

**2:45 – Close (15s)** Repo link, synthetic CC0 data, MIT code, reproducible with `exasol install local`.
