"""Build validation/LiqShield_Validation.xlsx: an independent, formula-driven re-computation of the engine.

Judges can change the preset selector (Inputs!B2) and watch the Excel buffer match the Exasol/SQL buffer
(stored as static values on Engine_Results) to the cent.
"""
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.liqshield import engine  # noqa: E402

HDR = PatternFill("solid", fgColor="1F2937")
INP = PatternFill("solid", fgColor="FEF3C7")
OK = PatternFill("solid", fgColor="DCFCE7")
MONEY = '#,##0;[Red]-#,##0'


def header(ws, row, cols):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font, cell.fill = Font(bold=True, color="FFFFFF"), HDR
        cell.alignment = Alignment(horizontal="center", wrap_text=True)


def build(path: Path, preset_index: int = 3) -> None:
    csv = lambda n: pd.read_csv(ROOT / "data" / f"{n}.csv")  # noqa: E731
    inv, hc, cf = csv("collateral_inventory"), csv("haircut_rules"), csv("cashflow_obligations")
    wb = Workbook()

    # ---------------- Inputs ----------------
    ws = wb.active
    ws.title = "Inputs"
    ws["A1"], ws["B1"] = "LiqShield validation model", "Independent Excel re-computation of the SQL engine"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"], ws["B2"] = "Scenario # (1=Base, 2=Moderate, 3=Severe)", preset_index
    ws["B2"].fill = INP
    dv = DataValidation(type="list", formula1='"1,2,3"', allow_blank=False)
    ws.add_data_validation(dv)
    dv.add("B2")
    header(ws, 4, ["#", "Preset", "Haircut shock (pp)", "Incoming delay (days)", "Margin multiplier"])
    for i, (n, p) in enumerate(engine.PRESETS.items(), 1):
        ws.append([i, n, p["haircut_shock"], p["delay_days"], p["margin_mult"]])
    ws["A9"], ws["B9"] = "Active haircut shock", "=INDEX(C5:C7,B2)"
    ws["A10"], ws["B10"] = "Active delay days", "=INDEX(D5:D7,B2)"
    ws["A11"], ws["B11"] = "Active margin multiplier", "=INDEX(E5:E7,B2)"
    ws["A13"] = "Rules: encumbered assets excluded; eligible = amount*(1-MIN(1,haircut+shock)); an asset counts from day = its settlement lag; " \
                "incoming cash shifts by the delay; margin calls scaled by the multiplier; buffer = mobilisable + cumulative net cashflow."
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 26
    for c in "CDE":
        ws.column_dimensions[c].width = 22

    # ---------------- Haircuts ----------------
    wh = wb.create_sheet("Haircuts")
    header(wh, 1, ["Asset type", "Rating", "Haircut %"])
    for r in hc.itertuples(index=False):
        wh.append(list(r))
    wh.column_dimensions["A"].width = 18

    # ---------------- Collateral ----------------
    wc = wb.create_sheet("Collateral")
    header(wc, 1, ["Asset ID", "Asset type", "Market value", "Encumbered", "Custodian", "Lag (days)",
                   "Base haircut", "Stressed haircut", "Eligible value"])
    for i, r in enumerate(inv.itertuples(index=False), start=2):
        wc.append([r.asset_id, r.asset_type, r.amount, bool(r.encumbered_flag), r.custodian, int(r.settlement_lag_days)])
        wc[f"G{i}"] = f"=VLOOKUP(B{i},Haircuts!$A$2:$C$6,3,FALSE)"
        wc[f"H{i}"] = f"=MIN(1,G{i}+Inputs!$B$9)"
        wc[f"I{i}"] = f"=IF(D{i},0,C{i}*(1-H{i}))"
        wc[f"C{i}"].number_format = wc[f"I{i}"].number_format = MONEY
    last = len(inv) + 1
    wc[f"H{last + 1}"], wc[f"I{last + 1}"] = "TOTAL ELIGIBLE", f"=SUM(I2:I{last})"
    wc[f"I{last + 1}"].number_format = MONEY
    wc[f"H{last + 1}"].font = wc[f"I{last + 1}"].font = Font(bold=True)
    for c, w in zip("ABCDEFGHI", [10, 16, 15, 12, 16, 10, 12, 16, 16]):
        wc.column_dimensions[c].width = w

    # ---------------- Cashflows ----------------
    wf = wb.create_sheet("Cashflows")
    header(wf, 1, ["Event", "Value day", "Direction", "Amount", "Type", "Counterparty", "Effective day", "Signed net"])
    for i, r in enumerate(cf.itertuples(index=False), start=2):
        wf.append([int(r.event_id), int(r.value_day), r.direction, r.amount, r.obligation_type, r.counterparty])
        wf[f"G{i}"] = f'=IF(C{i}="In",B{i}+Inputs!$B$10,B{i})'
        wf[f"H{i}"] = (f'=IF(C{i}="In",D{i},IF(OR(E{i}="MARGIN_CALL",E{i}="STRESS_MARGIN_CALL"),'
                       f'-D{i}*Inputs!$B$11,-D{i}))')
        wf[f"D{i}"].number_format = wf[f"H{i}"].number_format = MONEY
    for c in "ABCDEFGH":
        wf.column_dimensions[c].width = 16
    n_cf = len(cf) + 1

    # ---------------- Engine results (static values from the SQL engine) ----------------
    we = wb.create_sheet("Engine_Results")
    header(we, 1, ["Day", "Base buffer", "Moderate buffer", "Severe buffer"])
    ladders = [engine.ladder(**p) for p in engine.PRESETS.values()]
    for d in range(8):
        we.append([d] + [float(l.loc[l.day_offset == d, "liquidity_buffer"].iloc[0]) for l in ladders])
    for row in we.iter_rows(min_row=2, min_col=2, max_col=4):
        for c in row:
            c.number_format = MONEY
    we["F1"] = "Static values produced by the SQL engine (Exasol / DuckDB) via app.liqshield.engine.ladder()"
    for c in "ABCD":
        we.column_dimensions[c].width = 18

    # ---------------- Ladder ----------------
    wl = wb.create_sheet("Ladder", 1)
    header(wl, 1, ["Day", "Inflow", "Outflow", "Net cashflow", "Cumulative", "Mobilisable",
                   "Excel buffer", "Engine buffer", "Difference", "Status"])
    for d in range(8):
        r = d + 2
        wl[f"A{r}"] = d
        wl[f"B{r}"] = f"=SUMIFS(Cashflows!$H$2:$H${n_cf},Cashflows!$G$2:$G${n_cf},A{r},Cashflows!$H$2:$H${n_cf},\">0\")"
        wl[f"C{r}"] = f"=-SUMIFS(Cashflows!$H$2:$H${n_cf},Cashflows!$G$2:$G${n_cf},A{r},Cashflows!$H$2:$H${n_cf},\"<0\")"
        wl[f"D{r}"] = f"=B{r}-C{r}"
        wl[f"E{r}"] = f"=D{r}" if d == 0 else f"=E{r - 1}+D{r}"
        wl[f"F{r}"] = f'=SUMIFS(Collateral!$I$2:$I${last},Collateral!$F$2:$F${last},"<="&A{r})'
        wl[f"G{r}"] = f"=F{r}+E{r}"
        wl[f"H{r}"] = f"=INDEX(Engine_Results!$B{r}:$D{r},Inputs!$B$2)"
        wl[f"I{r}"] = f"=ROUND(G{r}-H{r},2)"
        wl[f"J{r}"] = f'=IF(G{r}<0,"SHORTFALL","ok")'
        for c in "BCDEFGHI":
            wl[f"{c}{r}"].number_format = MONEY
    wl["A11"], wl["B11"] = "Max |difference|", "=MAX(MAX(I2:I9),-MIN(I2:I9))"
    wl["A12"], wl["B12"] = "Lowest buffer", "=MIN(G2:G9)"
    wl["A13"], wl["B13"] = "First shortfall day", '=IFERROR(INDEX(A2:A9,MATCH(TRUE,INDEX(G2:G9<0,0),0)),"none")'
    wl["A14"], wl["B14"] = "Peak shortfall", "=MAX(0,-MIN(G2:G9))"
    wl["A15"], wl["B15"] = "VALIDATION", '=IF(B11=0,"PASS - Excel matches engine to the cent","FAIL")'
    wl["B15"].fill = OK
    for c in "B12 B14".split():
        wl[c].number_format = MONEY
    for c in "ABCDEFGHIJ":
        wl.column_dimensions[c].width = 17
    wl.column_dimensions["A"].width = 20
    wb.save(path)


if __name__ == "__main__":
    out = ROOT / "validation"
    out.mkdir(exist_ok=True)
    build(out / "LiqShield_Validation.xlsx", 3)
    print("wrote", out / "LiqShield_Validation.xlsx")
