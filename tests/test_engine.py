"""Validation: SQL result == independent oracle == hand-calculated constants."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.liqshield import engine, reference  # noqa: E402

SCENARIOS = list(engine.PRESETS.values()) + [
    {"haircut_shock": 0.03, "delay_days": 3, "margin_mult": 1.5},
]


def test_eligible_collateral_hand_calc():
    # Cash 5.0M + UST 10M*0.98 + AAA 4M*0.95 + BBB 2M*0.85 + Equities 3M*0.75; AST-003 (8M AAA) is encumbered.
    expected = 5_000_000 + 9_800_000 + 3_800_000 + 1_700_000 + 2_250_000
    assert expected == 22_550_000
    assert engine.eligible_collateral()["eligible_value"].sum() == pytest.approx(expected)


def test_encumbered_asset_excluded():
    df = engine.eligible_collateral().set_index("asset_id")
    assert df.loc["AST-003", "eligible_value"] == 0


@pytest.mark.parametrize("sc", SCENARIOS)
def test_ladder_matches_oracle(sc):
    sql = engine.ladder(**sc).reset_index(drop=True)
    ref = reference.ladder(**sc)
    for col in ["net_cashflow", "cum_cashflow", "mobilisable", "liquidity_buffer"]:
        assert sql[col].astype(float).tolist() == pytest.approx(ref[col].tolist()), col


def test_base_case_hand_calc():
    lad = engine.ladder()
    # Day 3: mobilisable 22.55M + cumulative net (0.7+0.3-0.6-15.1) = 22.55M - 14.7M = 7.85M
    assert lad.loc[lad.day_offset == 3, "liquidity_buffer"].iloc[0] == pytest.approx(7_850_000)
    m = engine.metrics()
    assert m["first_shortfall_day"] is None and m["peak_shortfall"] == 0


def test_severe_stress_metrics():
    m = engine.metrics(**engine.PRESETS["Severe stress"])
    assert m["first_shortfall_day"] == 4
    assert m["peak_shortfall"] == pytest.approx(4_490_000)
    assert m["shortfall_days"] == 4


def test_funding_covers_and_costs():
    f = engine.funding(**engine.PRESETS["Severe stress"])
    # Cheapest in-time facility is FAC-01 (5M @250bps, upfront 0) which alone covers 4.49M for 4 days (T+4..T+7).
    expected = 4_490_000 * 0.025 * 4 / 360
    assert f["total_cost"] == pytest.approx(expected)
    assert f["residual_gap"] == 0


def test_late_facility_not_used():
    # Harsh scenario: breach arrives on T+3, before FAC-05 (available T+4) can be drawn.
    sc = {"haircut_shock": 0.20, "delay_days": 2, "margin_mult": 1.3}
    f = engine.funding(**sc)
    assert f["metrics"]["first_shortfall_day"] == 3
    late = [w for w in f["waterfall"] if w["facility_id"] == "FAC-05"][0]
    assert late["in_time"] == 0 and late["draw_amount"] == 0
    for w in f["waterfall"]:
        assert w["in_time"] == (1 if w["available_from_day"] <= 3 else 0)


def test_monte_carlo_deterministic_and_bounded():
    a, b = engine.monte_carlo(0.05, 500, 7), engine.monte_carlo(0.05, 500, 7)
    assert a["p5_eligible"] == b["p5_eligible"]
    assert 0 < a["p5_eligible"] < a["base_eligible"]
