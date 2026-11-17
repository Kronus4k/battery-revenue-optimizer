"""Unit tests for the pure helpers in scripts/make_results.py (no database, no matplotlib)."""
import pytest

from scripts.make_results import (
    fmt_eur,
    fmt_gain,
    product_label,
    replace_between_markers,
    summary_table_md,
    window_label,
)

SE3_ROW = {
    "zone": "SE3", "days": 139, "arbitrage": 141.2, "best_reserve": "fcr_n",
    "best_reserve_v": 395.3, "wins": "128/139", "a_best": 434.0,
    "b_ceiling": 1031.6, "gain_pct": 138,
}


def test_eur_has_thousands_separator_and_one_decimal():
    assert fmt_eur(1031.6) == "1,031.6"
    assert fmt_eur(56.7) == "56.7"
    assert fmt_eur(434) == "434.0"


def test_gain_is_signed_percent():
    assert fmt_gain(138) == "+138 %"
    assert fmt_gain(0) == "+0 %"
    assert fmt_gain(-5) == "-5 %"


def test_product_labels_are_human_readable():
    assert product_label("fcr_n") == "FCR-N"
    assert product_label("fcr_d_up") == "FCR-D up"
    assert product_label("mfrr_down") == "mFRR down"
    assert product_label("arbitrage") == "Arbitrage"
    with pytest.raises(KeyError):
        product_label("unknown")


def test_summary_table_header_and_row():
    lines = summary_table_md([SE3_ROW]).splitlines()
    assert lines[0] == (
        "| Zone | Arbitrage only | Best reserve product (days best) "
        "| A: daily-commitment backtest (perfect foresight) "
        "| B: theoretical upper bound | Ceiling above A (B / A − 1) |"
    )
    assert lines[1] == "| --- | --- | --- | --- | --- | --- |"
    assert lines[2] == "| SE3 | 141.2 | FCR-N, 395.3 (128 of 139) | 434.0 | 1,031.6 | +138 % |"
    assert len(lines) == 3


def test_window_label():
    assert window_label("2026-07-01", "2026-11-16", "2026-11-17", 139) == (
        "139 days, 2026-07-01 → 2026-11-16, data as of 2026-11-17"
    )


def test_replace_between_markers_is_idempotent():
    text = "intro\n<!-- results:table:start -->\nold\n<!-- results:table:end -->\noutro\n"
    once = replace_between_markers(text, "table", "new")
    assert once == "intro\n<!-- results:table:start -->\nnew\n<!-- results:table:end -->\noutro\n"
    assert replace_between_markers(once, "table", "new") == once


@pytest.mark.parametrize("text", [
    "no markers at all",
    "<!-- results:table:start -->\nonly a start",
    "<!-- results:table:end -->\n<!-- results:table:start -->\n",   # wrong order
    "<!-- results:table:start -->\n<!-- results:table:end -->\n" * 2,  # twice
])
def test_replace_between_markers_rejects_bad_markers(text):
    with pytest.raises(ValueError):
        replace_between_markers(text, "table", "new")


# --- chart headlines are computed from the data, never typed -----------------
from scripts.make_results import title_a_vs_b, title_monthly, title_winners  # noqa: E402

SUMMARY = [
    {"zone": "SE1", "arbitrage": 56.7, "a_best": 542.4},
    {"zone": "SE3", "arbitrage": 141.2, "a_best": 434.0},
]


def test_title_a_vs_b_states_the_ratio_range():
    assert title_a_vs_b(SUMMARY) == "Strategy A earns 3–10 times as much as arbitrage alone in every zone"


def test_title_a_vs_b_falls_back_when_arbitrage_wins_somewhere():
    rows = SUMMARY + [{"zone": "SE4", "arbitrage": 900.0, "a_best": 900.0}]
    assert title_a_vs_b(rows) == "Strategy A compared with arbitrage alone, per zone"


def test_title_monthly_names_the_zone_whose_gap_grew_most():
    monthly = [
        {"zone": "SE1", "month": "2026-07", "a_best": 100, "b_ceiling": 150},
        {"zone": "SE1", "month": "2026-11", "a_best": 100, "b_ceiling": 160},
        {"zone": "SE3", "month": "2026-07", "a_best": 100, "b_ceiling": 180},
        {"zone": "SE3", "month": "2026-11", "a_best": 100, "b_ceiling": 370},
    ]
    assert title_monthly(monthly) == "The gap between A and the ceiling grew most in SE3"


def test_title_winners_states_how_rarely_arbitrage_wins():
    winners = [
        {"zone": "SE1", "strategy": "arbitrage", "days_won": 1},
        {"zone": "SE1", "strategy": "mfrr_down", "days_won": 138},
        {"zone": "SE4", "strategy": "arbitrage", "days_won": 3},
        {"zone": "SE4", "strategy": "mfrr_up", "days_won": 136},
    ]
    assert title_winners(winners, 139) == (
        "A reserve product is the best choice on almost every day; arbitrage wins at most 3 of 139"
    )


# --- chart subtitles: no commas (style rule) ---------------------------------
from scripts.make_results import chart_subtitles, chart_window  # noqa: E402


def test_chart_window_has_no_commas():
    assert chart_window("2026-07-01", "2026-11-16", "2026-11-17", 139) == (
        "139 days · 2026-07-01 → 2026-11-16 · data as of 2026-11-17"
    )


def test_no_chart_subtitle_contains_a_comma():
    subtitles = chart_subtitles(chart_window("2026-07-01", "2026-11-16", "2026-11-17", 139))
    assert set(subtitles) == {"a_vs_b", "monthly", "winners"}
    for name, text in subtitles.items():
        assert "," not in text, name


# --- README TL;DR: the bullets with numbers are generated --------------------
from scripts.make_results import tldr_md  # noqa: E402

TLDR_SUMMARY = [
    {"zone": "SE1", "arbitrage": 56.7, "a_best": 542.4, "b_ceiling": 717.6, "gain_pct": 32},
    {"zone": "SE3", "arbitrage": 141.2, "a_best": 434.0, "b_ceiling": 1031.6, "gain_pct": 138},
]
TLDR_WINNERS = [
    {"zone": "SE1", "strategy": "mfrr_down", "days_won": 82},
    {"zone": "SE1", "strategy": "fcr_n", "days_won": 56},
    {"zone": "SE1", "strategy": "arbitrage", "days_won": 1},
    {"zone": "SE3", "strategy": "fcr_n", "days_won": 136},
    {"zone": "SE3", "strategy": "arbitrage", "days_won": 3},
]


def test_tldr_bullets_are_computed_from_the_data():
    lines = tldr_md(TLDR_SUMMARY, TLDR_WINNERS, 139, "2026-07-01", "2026-11-16").splitlines()
    assert lines == [
        "- **Reserves beat arbitrage in every zone.** Committing to one strategy per day (A), a 1 MW / 2 MWh "
        "battery earned 434–542 EUR per day depending on zone, 3–10 times as much as spot arbitrage alone "
        "(139 days, 2026-07-01 → 2026-11-16). → [Results](#results)",
        "- **One product leads in each zone.** Most often mFRR down in SE1; FCR-N in SE3. Arbitrage was "
        "the best choice on at most 3 of 139 days in any zone. → [Which strategy wins](docs/results.md#which-strategy-wins)",
        "- **The ceiling is not a forecast.** B mixes products quarter by quarter and ignores state of charge. "
        "It is 32–138 % above A, widest in SE3. No real battery can earn it; it marks the room for an "
        "optimiser (Phase 2). → [Definitions](docs/results.md#definitions)",
    ]


def test_tldr_groups_zones_that_share_a_winner():
    winners = TLDR_WINNERS + [{"zone": "SE2", "strategy": "fcr_n", "days_won": 100}]
    summary = TLDR_SUMMARY + [{"zone": "SE2", "arbitrage": 61.5, "a_best": 456.4, "b_ceiling": 693.3, "gain_pct": 52}]
    assert "Most often mFRR down in SE1; FCR-N in SE2 and SE3." in tldr_md(summary, winners, 139, "a", "b")


def test_tldr_does_not_claim_reserves_win_when_arbitrage_is_ahead():
    summary = TLDR_SUMMARY + [{"zone": "SE4", "arbitrage": 900.0, "a_best": 900.0, "b_ceiling": 950.0, "gain_pct": 6}]
    assert "Reserves beat arbitrage" not in tldr_md(summary, TLDR_WINNERS, 139, "a", "b")
