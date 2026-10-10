"""
Battery Revenue Optimizer API (Day 4, D4.4).

GET /recommendation?zone=SE3&date=2026-10-09
    -> which strategy WOULD have earned most that day (strategy A, perfect
       foresight), all strategies ranked, and the theoretical ceiling (B).
GET /health
    -> 200 if the warehouse answers, 503 if not.

Design:
  - Reads ONLY analytics_marts, as the read-only role api_reader (D4.4).
    Its own env vars (API_DB_*), never the WAREHOUSE_* owner credentials.
  - Ranking and the winner come from the mart (revenue_rank, is_winner),
    computed and tested in dbt. The API shapes; it never re-decides.
  - Labels are LOCKED decisions: A = "daily-commitment backtest (perfect
    foresight)", B = "theoretical upper bound", never "expected revenue".
  - All SQL is parameterised (%s), never string-formatted: user input can't
    become SQL.
  - Pure functions (parse_params, shape_response) hold the logic, and the
    database sits behind a small "repo" object, so tests run without Postgres.
"""
import os
from datetime import date
from decimal import Decimal

from flask import Flask, jsonify, request

VALID_ZONES = ("SE1", "SE2", "SE3", "SE4")
LABEL_A = "daily-commitment backtest (perfect foresight)"
LABEL_B = "theoretical upper bound"
CAVEATS = [
    "retrospective: perfect foresight, not a forecast",
    "capacity payment only (no activation revenue)",
    "no state-of-charge or endurance rules for reserves",
    "price-taker: the battery does not move prices",
    "FCR price formation not yet verified",
]


# ---------------------------------------------------------------- pure logic
def parse_params(zone, date_str):
    """Validate query parameters. Returns (zone, date) or raises ValueError
    with a message that is safe to show to the caller."""
    if zone is None or date_str is None:
        raise ValueError("both 'zone' and 'date' are required, e.g. ?zone=SE3&date=2026-10-09")
    zone = zone.strip().upper()
    if zone not in VALID_ZONES:
        raise ValueError(f"zone must be one of {', '.join(VALID_ZONES)}")
    try:
        day = date.fromisoformat(date_str.strip())
    except ValueError:
        raise ValueError("date must be YYYY-MM-DD and a real calendar date") from None
    return zone, day


def _money(value):
    """Decimal from Postgres -> float with 2 decimals for JSON."""
    return round(float(value), 2)


def shape_response(zone, day, strategy_rows, upper_row):
    """
    strategy_rows: [(strategy, revenue_eur, revenue_rank, is_winner), ...]
    upper_row:     (n_quarters, upper_bound_eur) or None
    Returns the JSON-ready dict. Raises LookupError if there are no rows.
    """
    if not strategy_rows:
        raise LookupError("no backtest rows")
    rows = sorted(strategy_rows, key=lambda r: r[2])          # by rank
    winners = [r for r in rows if r[3]]
    winner = winners[0] if winners else rows[0]                # dbt guarantees one

    result = {
        "zone": zone,
        "date": day.isoformat(),
        "recommendation": {
            "strategy": winner[0],
            "revenue_eur": _money(winner[1]),
            "label": LABEL_A,
        },
        "strategies": [
            {"rank": int(r[2]), "strategy": r[0], "revenue_eur": _money(r[1])}
            for r in rows
        ],
        "upper_bound": None,
        "optimiser_headroom_pct": None,
        "caveats": CAVEATS,
    }
    if upper_row is not None:
        n_quarters, upper = upper_row
        result["upper_bound"] = {
            "revenue_eur": _money(upper),
            "n_quarters": int(n_quarters),
            "label": LABEL_B,
        }
        a = Decimal(winner[1])
        if a > 0:
            result["optimiser_headroom_pct"] = round(float((Decimal(upper) - a) / a * 100), 1)
    return result


# ---------------------------------------------------------------- database
class PostgresRepo:
    """The only code that talks to Postgres. One short connection per call:
    simple and enough for a local API (pooling = Phase 2)."""

    def __init__(self):
        self.params = dict(
            host=os.environ.get("API_DB_HOST", "127.0.0.1"),
            port=int(os.environ.get("API_DB_PORT", "5433")),
            dbname=os.environ.get("API_DB_NAME", "battery"),
            user=os.environ.get("API_DB_USER", "api_reader"),
            password=os.environ["API_DB_PASSWORD"],        # KeyError = not configured
            connect_timeout=5,
        )

    def _query(self, sql, args=()):
        import psycopg2                                    # imported here: tests don't need it
        conn = psycopg2.connect(**self.params)
        try:
            with conn.cursor() as cur:
                cur.execute(sql, args)                     # parameterised, never f-strings
                return cur.fetchall()
        finally:
            conn.close()

    def ping(self):
        return self._query("select 1") == [(1,)]

    def day(self, zone, day):
        rows = self._query(
            "select strategy, revenue_eur, revenue_rank, is_winner "
            "from analytics_marts.mart_strategy_daily "
            "where bidding_zone = %s and delivery_date = %s",
            (zone, day))
        upper = self._query(
            "select n_quarters, upper_bound_eur "
            "from analytics_marts.mart_upper_bound_daily "
            "where bidding_zone = %s and delivery_date = %s",
            (zone, day))
        return rows, (upper[0] if upper else None)

    def date_range(self, zone):
        (first, last), = self._query(
            "select min(delivery_date), max(delivery_date) "
            "from analytics_marts.mart_strategy_daily where bidding_zone = %s",
            (zone,))
        return first, last


# ---------------------------------------------------------------- web layer
def create_app(repo=None):
    """App factory: tests pass a fake repo; production builds PostgresRepo."""
    app = Flask(__name__)
    app.json.sort_keys = False                             # keep our field order
    repo = repo or PostgresRepo()

    @app.get("/health")
    def health():
        try:
            ok = repo.ping()
        except Exception:                                  # DB down = unhealthy, not a crash
            ok = False
        return jsonify(status="ok" if ok else "warehouse unreachable"), (200 if ok else 503)

    @app.get("/recommendation")
    def recommendation():
        try:
            zone, day = parse_params(request.args.get("zone"), request.args.get("date"))
        except ValueError as e:
            return jsonify(error=str(e)), 400

        rows, upper = repo.day(zone, day)
        if not rows:
            first, last = repo.date_range(zone)
            return jsonify(
                error=f"no backtest for {zone} on {day.isoformat()}",
                available_from=first.isoformat() if first else None,
                available_to=last.isoformat() if last else None,
                hint="backtest days need both spot and SvK data; SvK arrives the next morning",
            ), 404
        return jsonify(shape_response(zone, day, rows, upper)), 200

    return app


if __name__ == "__main__":                                # local dev only; Docker uses gunicorn
    create_app().run(host="127.0.0.1", port=5000, debug=False)
