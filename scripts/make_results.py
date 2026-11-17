"""Generate the published results from the warehouse marts.

Usage (repository root, after load_env and dbt build):
    python scripts/make_results.py 2026-07-01 2026-11-16 --as-of 2026-11-17

Reads analytics_marts with the WAREHOUSE_* environment variables (same as
load_raw.py), then
  * writes the tables between <!-- results:<name>:start/end --> markers in
    README.md and docs/results.md (no number is typed by hand),
  * draws three SVG charts into docs/images/.
Re-running with the same data gives byte-identical files (deterministic SVG).
The SQL lives in sql/results/; summary.sql is the single source of the table.
"""
import argparse
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql" / "results"
IMG_DIR = ROOT / "docs" / "images"

# Reference window: the first published results (99 days), kept for comparison.
COMPARE_START, COMPARE_END = "2026-07-01", "2026-10-07"

PRODUCT_LABELS = {
    "arbitrage": "Arbitrage",
    "fcr_n": "FCR-N",
    "fcr_d_up": "FCR-D up",
    "fcr_d_down": "FCR-D down",
    "mfrr_up": "mFRR up",
    "mfrr_down": "mFRR down",
}

SUMMARY_HEADER = (
    "| Zone | Arbitrage only | Best reserve product (days best) "
    "| A: daily-commitment backtest (perfect foresight) "
    "| B: theoretical upper bound | Ceiling above A (B / A − 1) |"
)


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested; no database, no matplotlib)
# ---------------------------------------------------------------------------
def fmt_eur(value):
    """1031.6 -> '1,031.6' (one decimal, thousands separator)."""
    return f"{float(value):,.1f}"


def fmt_gain(pct):
    """138 -> '+138 %'."""
    return f"{int(pct):+d} %"


def product_label(code):
    return PRODUCT_LABELS[code]


def window_label(start, end, as_of, days):
    return f"{days} days, {start} → {end}, data as of {as_of}"


def chart_window(start, end, as_of, days):
    """The window for chart subtitles: same facts, no commas (chart style rule)."""
    return f"{days} days · {start} → {end} · data as of {as_of}"


def chart_subtitles(window):
    """Subtitles of the three charts; they never contain a comma."""
    return {
        "a_vs_b": f"Average revenue in EUR per day · {window}",
        "monthly": ("Monthly average in EUR per day · A: daily-commitment backtest (solid) · "
                    f"B: theoretical upper bound (dashed)\n{window}"),
        "winners": f"Days on which each strategy was the best single choice · {window}",
    }


def summary_table_md(rows):
    lines = [SUMMARY_HEADER, "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        won, total = str(r["wins"]).split("/")
        lines.append(
            f"| {r['zone']} | {fmt_eur(r['arbitrage'])} "
            f"| {product_label(r['best_reserve'])}, {fmt_eur(r['best_reserve_v'])} ({won} of {total}) "
            f"| {fmt_eur(r['a_best'])} | {fmt_eur(r['b_ceiling'])} | {fmt_gain(r['gain_pct'])} |"
        )
    return "\n".join(lines)


def replace_between_markers(text, name, body):
    """Replace the text between <!-- results:NAME:start --> and ...:end -->.

    Both markers must appear exactly once, start before end; otherwise ValueError
    (so a typo never silently leaves stale numbers in place).
    """
    start, end = f"<!-- results:{name}:start -->", f"<!-- results:{name}:end -->"
    if text.count(start) != 1 or text.count(end) != 1:
        raise ValueError(f"markers for '{name}' must each appear exactly once")
    i, j = text.index(start), text.index(end)
    if j < i:
        raise ValueError(f"end marker for '{name}' comes before its start marker")
    return text[: i + len(start)] + "\n" + body + "\n" + text[j:]


# ---------------------------------------------------------------------------
# Further table builders
# ---------------------------------------------------------------------------
def coverage_md(rows):
    if not rows:
        return "Every reserve product has all hours of every day."
    parts = [
        f"{r['zone']} {product_label(r['product'])}: {int(r['n_hours']):,} of "
        f"{int(r['expected_hours']):,} hours published ({int(r['short_days'])} days with gaps)"
        for r in rows
    ]
    return "; ".join(parts) + ". Unpublished hours count as 0 revenue."


def comparison_md(old, new, old_days, new_days):
    old_by = {r["zone"]: r for r in old}
    lines = [
        f"| Zone | A, {old_days} days | A, {new_days} days | Change in A "
        f"| B, {old_days} days | B, {new_days} days | Best reserve product ({old_days} / {new_days} days) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for n in new:
        o = old_by[n["zone"]]
        change = 100 * (float(n["a_best"]) / float(o["a_best"]) - 1)
        lines.append(
            f"| {n['zone']} | {fmt_eur(o['a_best'])} | {fmt_eur(n['a_best'])} | {change:+.1f} % "
            f"| {fmt_eur(o['b_ceiling'])} | {fmt_eur(n['b_ceiling'])} "
            f"| {product_label(o['best_reserve'])} / {product_label(n['best_reserve'])} |"
        )
    return "\n".join(lines)


def monthly_md(rows):
    lines = [
        "| Zone | Month | Days | Arbitrage only | A | B | Ceiling above A |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        gain = round(100 * (float(r["b_ceiling"]) / float(r["a_best"]) - 1))
        lines.append(
            f"| {r['zone']} | {r['month']} | {r['days']} | {fmt_eur(r['arbitrage'])} "
            f"| {fmt_eur(r['a_best'])} | {fmt_eur(r['b_ceiling'])} | {fmt_gain(gain)} |"
        )
    return "\n".join(lines)


def winners_md(rows, zones, strategies):
    days = {(r["zone"], r["strategy"]): int(r["days_won"]) for r in rows}
    lines = [
        "| Zone | " + " | ".join(product_label(s) for s in strategies) + " |",
        "| --- |" + " --- |" * len(strategies),
    ]
    for z in zones:
        lines.append(f"| {z} | " + " | ".join(str(days.get((z, s), 0)) for s in strategies) + " |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def connect():
    import psycopg2
    return psycopg2.connect(
        host=os.environ.get("WAREHOUSE_HOST", "127.0.0.1"),
        port=int(os.environ.get("WAREHOUSE_PORT", "5433")),
        user=os.environ["WAREHOUSE_USER"],          # KeyError = forgot load_env
        password=os.environ["WAREHOUSE_PASSWORD"],
        dbname=os.environ["WAREHOUSE_DB"],
    )


def query(conn, name, start, end):
    sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql, {"start": start, "end": end})
        cols = [c.name for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


# ---------------------------------------------------------------------------
# Charts: report style. A headline that states the finding (computed from the
# data), a grey subtitle with units, no frame, values labelled directly, a
# restrained navy/blue palette and a source note. Series differ in lightness
# and form (solid / outlined bar, solid / dashed line) and carry direct labels,
# so no chart depends on colour alone.
# ---------------------------------------------------------------------------
NAVY = "#0B1F33"
BLUE = "#2E5EAA"
SKY = "#7FA7DB"
PALE = "#C9D6E8"
GREY = "#A3A9B0"
INK = "#1A1A1A"
MUTED = "#5F6670"
STRATEGY_COLOUR = {
    "fcr_n": NAVY, "mfrr_up": BLUE, "mfrr_down": SKY,
    "fcr_d_up": PALE, "fcr_d_down": "#E3EAF3", "arbitrage": GREY,
}
SOURCE_NOTE = ("Source: elprisetjustnu.se; Svenska kraftnät (Mimer, SVK Data Service); own backtest. "
               "1 MW / 2 MWh battery, round-trip efficiency 0.85, perfect foresight, capacity payments only.")


def title_a_vs_b(summary):
    ratios = [float(r["a_best"]) / float(r["arbitrage"]) for r in summary if float(r["arbitrage"]) > 0]
    if len(ratios) != len(summary) or min(ratios) <= 1:
        return "Strategy A compared with arbitrage alone, per zone"
    return f"Strategy A earns {round(min(ratios))}–{round(max(ratios))} times as much as arbitrage alone in every zone"


def title_monthly(monthly):
    growth = {}
    for z in sorted({r["zone"] for r in monthly}):
        rows = sorted((r for r in monthly if r["zone"] == z), key=lambda r: r["month"])
        gap = [float(r["b_ceiling"]) - float(r["a_best"]) for r in rows]
        growth[z] = gap[-1] - gap[0]
    return f"The gap between A and the ceiling grew most in {max(growth, key=growth.get)}"


def title_winners(winners, n_days):
    arb = max((int(r["days_won"]) for r in winners if r["strategy"] == "arbitrage"), default=0)
    if arb <= 0.05 * n_days:
        return f"A reserve product is the best choice on almost every day; arbitrage wins at most {arb} of {n_days}"
    return "Days on which each strategy was the best single choice"


def _pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "svg.hashsalt": "battery-optimizer",   # stable element ids
        "svg.fonttype": "none",                # text stays text (smaller, searchable)
        "font.family": ["Arial", "DejaVu Sans"],   # Arial on Windows; DejaVu ships with matplotlib
        "font.size": 9.5,
        "text.color": INK, "axes.labelcolor": MUTED,
        "xtick.color": MUTED, "ytick.color": MUTED,
        "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False,
        "axes.edgecolor": GREY, "axes.linewidth": 0.8,
    })
    return plt


def _frame(fig, headline, subtitle):
    """Headline, subtitle and source note, left-aligned in figure coordinates."""
    fig.text(0.01, 0.985, headline, ha="left", va="top", fontsize=12.5, fontweight="bold", color=INK)
    fig.text(0.01, 0.925, subtitle, ha="left", va="top", fontsize=9.5, color=MUTED)
    fig.text(0.01, 0.01, SOURCE_NOTE, ha="left", va="bottom", fontsize=7.5, color=MUTED, wrap=True)


def _save(fig, name):
    path = IMG_DIR / name
    fig.savefig(path, format="svg", metadata={"Date": None}, facecolor="white")
    return path


def chart_a_vs_b(summary, subtitle):
    plt = _pyplot()
    zones = [r["zone"] for r in summary]
    series = [   # name, key, fill, edge
        ("Arbitrage only", "arbitrage", GREY, GREY),
        ("A: daily-commitment backtest (perfect foresight)", "a_best", NAVY, NAVY),
        ("B: theoretical upper bound (ignores state of charge)", "b_ceiling", "white", NAVY),
    ]
    fig, ax = plt.subplots(figsize=(8.6, 4.9))
    fig.subplots_adjust(left=0.03, right=0.99, top=0.76, bottom=0.14)
    width = 0.27
    for k, (name, key, fill, edge) in enumerate(series):
        xs = [i + (k - 1) * width for i in range(len(zones))]
        vals = [float(r[key]) for r in summary]
        bars = ax.bar(xs, vals, width * 0.92, label=name, color=fill, edgecolor=edge, linewidth=1.2)
        ax.bar_label(bars, labels=[f"{v:,.0f}" for v in vals], padding=2, fontsize=8.5, color=INK)
    ax.set_xticks(range(len(zones)), zones, fontsize=10, color=INK)
    ax.tick_params(axis="x", length=0)
    ax.set_yticks([])
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=3, fontsize=8.5,
              handlelength=1.2, columnspacing=1.4)
    _frame(fig, title_a_vs_b(summary), subtitle)
    return _save(fig, "results_a_vs_b.svg")


def chart_monthly(monthly, subtitle):
    plt = _pyplot()
    zones = sorted({r["zone"] for r in monthly})
    months = sorted({r["month"] for r in monthly})
    days_in = {m: max(int(r["days"]) for r in monthly if r["month"] == m) for m in months}
    ticks = [date.fromisoformat(m + "-01").strftime("%b") + ("" if days_in[m] >= 28 else f"\n({days_in[m]} days)")
             for m in months]
    fig, axes = plt.subplots(1, len(zones), figsize=(9.6, 4.4), sharey=True)
    fig.subplots_adjust(left=0.03, right=0.95, top=0.72, bottom=0.2, wspace=0.18)
    x = list(range(len(months)))
    for ax, z in zip(axes, zones):
        rows = {r["month"]: r for r in monthly if r["zone"] == z}
        a = [float(rows[m]["a_best"]) for m in months]
        b = [float(rows[m]["b_ceiling"]) for m in months]
        ax.plot(x, b, "--", color=BLUE, linewidth=1.6)
        ax.plot(x, a, "-", color=NAVY, linewidth=2.2, marker="o", markersize=3.5)
        # Both end labels sit above their line, never on the x axis.
        for series, vals, colour, dy in (("B", b, BLUE, 6), ("A", a, NAVY, 6)):
            ax.annotate(f"{series} {vals[-1]:,.0f}", (x[-1], vals[-1]), xytext=(4, dy),
                        textcoords="offset points", fontsize=8, color=colour, fontweight="bold")
        ax.set_title(z, loc="left", fontsize=10.5, fontweight="bold", color=INK)
        ax.set_xticks(x, ticks, fontsize=8)
        ax.tick_params(axis="both", length=0)
        ax.grid(axis="y", color="#E6E9ED", linewidth=0.8)
        ax.set_xlim(-0.3, len(months) - 0.3)
    axes[0].tick_params(axis="y", labelsize=8)
    _frame(fig, title_monthly(monthly), subtitle)
    return _save(fig, "results_monthly.svg")


def chart_winners(winners, zones, strategies, n_days, subtitle):
    plt = _pyplot()
    days = {(r["zone"], r["strategy"]): int(r["days_won"]) for r in winners}
    # Biggest overall winner first, arbitrage last.
    order = sorted((s for s in strategies if s != "arbitrage"),
                   key=lambda s: -sum(days.get((z, s), 0) for z in zones))
    order += [s for s in strategies if s == "arbitrage"]
    fig, ax = plt.subplots(figsize=(8.6, 4.2))
    fig.subplots_adjust(left=0.07, right=0.99, top=0.72, bottom=0.2)
    left = [0] * len(zones)
    for s in order:
        colour = STRATEGY_COLOUR[s]
        vals = [days.get((z, s), 0) for z in zones]
        bars = ax.barh(zones, vals, left=left, height=0.62, label=product_label(s), color=colour,
                       edgecolor="white", linewidth=1.0)
        dark = colour in (NAVY, BLUE)
        ax.bar_label(bars, labels=[f"{product_label(s)} {v}" if v >= 18 else (str(v) if v >= 5 else "")
                                   for v in vals],
                     label_type="center", fontsize=8, color="white" if dark else INK)
        left = [l + v for l, v in zip(left, vals)]
    ax.invert_yaxis()
    ax.set_xlim(0, n_days)
    ax.set_xticks([])
    ax.spines["bottom"].set_visible(False)
    ax.tick_params(axis="y", length=0, labelsize=10, labelcolor=INK)
    ax.legend(frameon=False, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=len(order), fontsize=8,
              handlelength=1.0, columnspacing=1.2)
    _frame(fig, title_winners(winners, n_days), subtitle)
    return _save(fig, "results_winners.svg")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def write_markers(path, blocks):
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    text = raw.decode("utf-8").replace("\r\n", "\n")
    for name, body in blocks.items():
        text = replace_between_markers(text, name, body)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("start")
    p.add_argument("end")
    p.add_argument("--as-of", required=True, help="date the data was fetched")
    args = p.parse_args(argv)
    # The Windows console (cp1252) cannot print '→'; never crash on output.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    conn = connect()
    try:
        summary = query(conn, "summary", args.start, args.end)
        compare = query(conn, "summary", COMPARE_START, COMPARE_END)
        monthly = query(conn, "monthly", args.start, args.end)
        winners = query(conn, "winners", args.start, args.end)
        coverage = query(conn, "coverage", args.start, args.end)
    finally:
        conn.close()

    n_days = {int(r["days"]) for r in summary}
    if len(n_days) != 1:
        sys.exit(f"zones cover different numbers of days: {sorted(n_days)}")
    n_days = n_days.pop()
    zones = [r["zone"] for r in summary]
    for z in zones:   # one winner per day (a tie would double count)
        total = sum(int(r["days_won"]) for r in winners if r["zone"] == z)
        if total != n_days:
            sys.exit(f"{z}: winners sum to {total}, expected {n_days}")
    strategies = [s for s in PRODUCT_LABELS if any(r["strategy"] == s for r in winners)]
    old_days = int(compare[0]["days"])

    label = window_label(args.start, args.end, args.as_of, n_days)
    common = {
        "window": f"**{label}.** Averages in EUR per day for a 1 MW / 2 MWh battery.",
        "summary": summary_table_md(summary),
        "coverage": coverage_md(coverage),
    }
    write_markers(ROOT / "README.md", common)
    write_markers(ROOT / "docs" / "results.md", {
        **common,
        "comparison": comparison_md(compare, summary, old_days, n_days),
        "monthly": monthly_md(monthly),
        "winners": winners_md(winners, zones, strategies),
    })
    subs = chart_subtitles(chart_window(args.start, args.end, args.as_of, n_days))
    for path in (chart_a_vs_b(summary, subs["a_vs_b"]), chart_monthly(monthly, subs["monthly"]),
                 chart_winners(winners, zones, strategies, n_days, subs["winners"])):
        print(f"wrote {path.relative_to(ROOT).as_posix()}")
    print(label)
    print(summary_table_md(summary))


if __name__ == "__main__":
    main()
