import json
import math
import sqlite3
from statistics import median
from datetime import datetime, timedelta, timezone
from market_data import get_price, get_bar_after
from crypto_data import get_crypto_price, get_kline_after
from db import init_db, log_outcome, connect
from config import CRYPTO_SYMBOLS

# Versioned directional evaluation, not realized profit or prediction-text grading.
MIN_AGE = "-3 day"
HORIZON_DAYS = 3
MAX_BAR_LAG_DAYS = 5
MIN_MEANINGFUL_PCT = 0.25
NOISE_MULTIPLE = 1.0


def is_crypto(symbol):
    return symbol in CRYPTO_SYMBOLS or symbol.endswith("USDT")


def current_price(symbol):
    """Crypto lives on Binance, stocks on Alpaca -- asking the wrong one 404s."""
    return get_crypto_price(symbol) if is_crypto(symbol) else get_price(symbol)


def horizon_price(symbol, decision_time):
    """Use a completed horizon candle; missing history stays pending."""
    target = decision_time + timedelta(days=HORIZON_DAYS)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if target > now:
        raise ValueError("prediction horizon has not elapsed")
    if is_crypto(symbol):
        bar = get_kline_after(symbol, target.replace(tzinfo=timezone.utc).timestamp() * 1000)
    else:
        bar = get_bar_after(symbol, target.strftime("%Y-%m-%d"))
    if bar is None:
        raise ValueError("historical horizon candle unavailable")
    opened = bar_time(bar)
    if opened.date() < target.date() or opened > target + timedelta(days=4):
        raise ValueError("returned candle is outside horizon window")
    if opened + timedelta(days=1) > now:
        raise ValueError("horizon candle is not complete yet")
    price = float(bar["c"])
    if not math.isfinite(price) or price <= 0:
        raise ValueError("invalid horizon price")
    return price, opened.isoformat()


def bar_time(bar):
    """Stock bars timestamp as an ISO string, Binance klines as epoch millis."""
    t = bar["t"]
    if isinstance(t, (int, float)):
        return datetime.fromtimestamp(t / 1000, tz=timezone.utc).replace(tzinfo=None)
    return datetime.fromisoformat(str(t).replace("Z", "+00:00")).replace(tzinfo=None)


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
    spacing = median((bar_time(bars[i]) - bar_time(bars[i-1])).total_seconds() for i in range(1, len(bars)))
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
    if action not in ("buy", "sell", "hold") or not math.isfinite(pct_change):
        raise ValueError("invalid score input")
    if action == "buy":
        return "yes" if pct_change > threshold else "no"
    if action == "sell":
        return "yes" if pct_change < -threshold else "no"
    return "yes" if abs(pct_change) <= threshold else "no"


def check_all():
    init_db()
    conn = connect()
    cursor = conn.cursor()
    cursor.execute("""CREATE TABLE IF NOT EXISTS evaluations_v2 (
        decision_id INTEGER PRIMARY KEY, checked_at TEXT, price_at_decision REAL,
        horizon_price REAL, horizon_bar TEXT, pct_change REAL, threshold REAL,
        correct TEXT, method TEXT)""")
    conn.commit()
    cursor.execute(f"""
        SELECT d.id, d.timestamp, d.symbol, d.market_state, d.action, d.price_at_decision
        FROM decisions d
        WHERE d.timestamp <= datetime('now', '{MIN_AGE}')
          AND json_valid(d.market_state)
          AND json_extract(d.market_state, '$.evaluation_version') = 'direction-v2'
          AND NOT EXISTS (SELECT 1 FROM evaluations_v2 o WHERE o.decision_id = d.id)
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
            if not isinstance(state, dict) or state.get("evaluation_version") != "direction-v2" or row_price is None:
                continue  # Legacy testnet prices cannot be fairly graded against public prices.
            price_at_decision = float(row_price)
            if not math.isfinite(price_at_decision) or price_at_decision <= 0:
                raise ValueError("invalid decision price")

            decision_day = datetime.fromisoformat(timestamp[:10])
            if (decision_day - bar_time(bars[-1])).days > MAX_BAR_LAG_DAYS:
                # Leave malformed data ungraded.
                print(f"#{decision_id} {symbol}: marked invalid (stale bars at decision time)")
                continue

            price_now, at = horizon_price(symbol, datetime.fromisoformat(timestamp))
            pct_change = ((price_now - price_at_decision) / price_at_decision) * 100
            threshold = meaningful_move(bars)
            correct = score(action, pct_change, threshold)

            with connect() as output:
                output.execute("""INSERT OR IGNORE INTO evaluations_v2 VALUES
                    (?, datetime('now'), ?, ?, ?, ?, ?, ?, ?)""",
                    (decision_id, price_at_decision, price_now, at, pct_change,
                     threshold, correct, "direction-v2: daily close after 72h; not P/L"))
            print(f"#{decision_id} {symbol}: {action} {pct_change:+.2f}% vs {threshold:.2f}% bar (at {at}) -> {correct}")
            scored += 1
        except Exception as e:
            failed += 1
            print(f"#{decision_id} {symbol}: SKIPPED ({type(e).__name__}: {e})")

    print(f"scored {scored}, skipped {failed}")


if __name__ == "__main__":
    check_all()
