import json
import math
import sqlite3
from statistics import median
from datetime import datetime, timedelta, timezone
from market_data import get_price, get_bar_after
from crypto_data import get_crypto_price, get_kline_after
from db import init_db, log_outcome, connect
from config import CRYPTO_SYMBOLS

# Only score decisions at least this old. Most predictions state a 3-5 day
# horizon themselves; checking sooner than that tests a claim before it had
# time to happen, and unfairly favors hold (easy to "clear" in 1 day) over
# buy/sell (rarely move 1%+ that fast).
MIN_AGE = "-3 day"

# Score each prediction at a fixed horizon after the decision, not at "whatever
# the price happens to be when you run this". Otherwise a backlog checked weeks
# late grades a "next few days" call on a multi-week move, and the same row
# would score differently on every run.
HORIZON_DAYS = 3

# If the newest bar the model saw was this much older than the decision itself,
# the input data was stale (early bug) and the outcome can't be trusted.
MAX_BAR_LAG_DAYS = 5

# A move smaller than this doesn't count as a real "correct" call in any
# direction -- otherwise buy/sell win on any tiny wobble and hold wins on
# any quiet day, regardless of whether the reasoning behind it meant anything.
#
# One flat number cannot serve both markets: over three days a stock typically
# moves ~0.2% while BTC moves ~6%. A fixed 1% therefore handed every stock hold
# a free win and marked every crypto hold wrong, measuring volatility rather
# than skill. So the bar is set per asset from its own recent volatility, with
# this as an absolute floor.
MIN_MEANINGFUL_PCT = 0.25
NOISE_MULTIPLE = 1.0


def is_crypto(symbol):
    return symbol in CRYPTO_SYMBOLS or symbol.endswith("USDT")


def current_price(symbol):
    """Crypto lives on Binance, stocks on Alpaca -- asking the wrong one 404s."""
    return get_crypto_price(symbol) if is_crypto(symbol) else get_price(symbol)


def horizon_price(symbol, decision_time):
    """Close of the first daily bar at least HORIZON_DAYS after the decision.

    Returns (price, label). Falls back to the live price when the horizon bar
    isn't published yet, so recent decisions still score.
    """
    target = decision_time + timedelta(days=HORIZON_DAYS)
    if target > datetime.now(timezone.utc).replace(tzinfo=None):
        return current_price(symbol), "live"
    if is_crypto(symbol):
        bar = get_kline_after(symbol, target.replace(tzinfo=timezone.utc).timestamp() * 1000)
    else:
        bar = get_bar_after(symbol, target.strftime("%Y-%m-%d"))
    if bar is None:
        return current_price(symbol), "live"
    return bar["c"], bar_time(bar).strftime("%Y-%m-%d")


def bar_time(bar):
    """Stock bars timestamp as an ISO string, Binance klines as epoch millis."""
    t = bar["t"]
    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(t / 1000, tz=timezone.utc).replace(tzinfo=None)
    return datetime.fromisoformat(str(t)[:10])


def reference_price(row_price, bars):
    """Price the decision was actually made at.

    Falls back to the last close only for rows written before that price was
    recorded; for the 5-minute crypto loop that close can be ~9h stale, which
    silently credits or blames a decision for a move it never saw.
    """
    if row_price is not None:
        return float(row_price)
    return bars[-1]["c"]


def typical_move_pct(bars):
    """Median absolute move between consecutive bars -- this asset's noise."""
    closes = [b["c"] for b in bars]
    steps = [abs((closes[i] - closes[i - 1]) / closes[i - 1]) * 100
             for i in range(1, len(closes)) if closes[i - 1]]
    return median(steps) if steps else 0.0


def bars_per_horizon(bars):
    """How many of these bars span the horizon, read from their own spacing.

    Lets the same code handle daily stock bars and hourly crypto candles.
    """
    if len(bars) < 2:
        return 1.0
    spacing = (bar_time(bars[-1]) - bar_time(bars[-2])).total_seconds()
    if spacing <= 0:
        return 1.0
    return max(1.0, (HORIZON_DAYS * 86400) / spacing)


def meaningful_move(bars):
    """How big a move has to be, for this asset, to mean anything.

    Per-bar noise scaled to the horizon the random-walk way (sqrt of time).
    """
    scaled = typical_move_pct(bars) * math.sqrt(bars_per_horizon(bars)) * NOISE_MULTIPLE
    return max(MIN_MEANINGFUL_PCT, scaled)


def score(action, pct_change, threshold=MIN_MEANINGFUL_PCT):
    if action == "buy":
        return "yes" if pct_change > threshold else "no"
    if action == "sell":
        return "yes" if pct_change < -threshold else "no"
    return "yes" if abs(pct_change) <= threshold else "no"


def check_all():
    init_db()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT d.id, d.timestamp, d.symbol, d.market_state, d.action, d.price_at_decision
        FROM decisions d
        WHERE d.timestamp <= datetime('now', '{MIN_AGE}')
          AND NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.decision_id = d.id)
    """)
    rows = cursor.fetchall()
    conn.close()

    print(f"{len(rows)} decision(s) ready to check")
    scored = failed = 0
    for decision_id, timestamp, symbol, market_state, action, row_price in rows:
        # One unreachable symbol or malformed row must not abandon the rest of
        # the queue -- that is how the whole backlog went unscored before.
        try:
            state = json.loads(market_state)
            bars = state["bars"] if isinstance(state, dict) else state
            price_at_decision = reference_price(row_price, bars)

            decision_day = datetime.fromisoformat(timestamp[:10])
            if (decision_day - bar_time(bars[-1])).days > MAX_BAR_LAG_DAYS:
                log_outcome(decision_id, price_at_decision, None, None, "invalid")
                print(f"#{decision_id} {symbol}: marked invalid (stale bars at decision time)")
                continue

            price_now, at = horizon_price(symbol, datetime.fromisoformat(timestamp))
            pct_change = ((price_now - price_at_decision) / price_at_decision) * 100
            threshold = meaningful_move(bars)
            correct = score(action, pct_change, threshold)

            log_outcome(decision_id, price_at_decision, price_now, pct_change, correct)
            print(f"#{decision_id} {symbol}: {action} {pct_change:+.2f}% vs {threshold:.2f}% bar (at {at}) -> {correct}")
            scored += 1
        except Exception as e:
            failed += 1
            print(f"#{decision_id} {symbol}: SKIPPED ({type(e).__name__}: {e})")

    print(f"scored {scored}, skipped {failed}")


if __name__ == "__main__":
    check_all()
