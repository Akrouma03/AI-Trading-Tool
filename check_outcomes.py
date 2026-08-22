import json
import sqlite3
from datetime import datetime
from market_data import get_price
from db import init_db, log_outcome
from config import DB_FILE

# Only score decisions at least this old. Most predictions state a 3-5 day
# horizon themselves; checking sooner than that tests a claim before it had
# time to happen, and unfairly favors hold (easy to "clear" in 1 day) over
# buy/sell (rarely move 1%+ that fast).
MIN_AGE = "-3 day"

# If the newest bar the model saw was this much older than the decision itself,
# the input data was stale (early bug) and the outcome can't be trusted.
MAX_BAR_LAG_DAYS = 5

# A move smaller than this doesn't count as a real "correct" call in any
# direction -- otherwise buy/sell win on any tiny wobble and hold wins on
# any quiet day, regardless of whether the reasoning behind it meant anything.
MEANINGFUL_MOVE_PCT = 1.0


def score(action, pct_change):
    if action == "buy":
        return "yes" if pct_change > MEANINGFUL_MOVE_PCT else "no"
    if action == "sell":
        return "yes" if pct_change < -MEANINGFUL_MOVE_PCT else "no"
    return "yes" if abs(pct_change) <= MEANINGFUL_MOVE_PCT else "no"


def check_all():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute(f"""
        SELECT d.id, d.timestamp, d.symbol, d.market_state, d.action
        FROM decisions d
        WHERE d.timestamp <= datetime('now', '{MIN_AGE}')
          AND NOT EXISTS (SELECT 1 FROM outcomes o WHERE o.decision_id = d.id)
    """)
    rows = cursor.fetchall()
    conn.close()

    print(f"{len(rows)} decision(s) ready to check")
    for decision_id, timestamp, symbol, market_state, action in rows:
        state = json.loads(market_state)
        bars = state["bars"] if isinstance(state, dict) else state
        price_at_decision = bars[-1]["c"]

        bar_day = datetime.fromisoformat(bars[-1]["t"][:10])
        decision_day = datetime.fromisoformat(timestamp[:10])
        if (decision_day - bar_day).days > MAX_BAR_LAG_DAYS:
            log_outcome(decision_id, price_at_decision, None, None, "invalid")
            print(f"#{decision_id} {symbol}: marked invalid (stale bars at decision time)")
            continue

        price_now = get_price(symbol)
        pct_change = ((price_now - price_at_decision) / price_at_decision) * 100

        correct = score(action, pct_change)

        log_outcome(decision_id, price_at_decision, price_now, pct_change, correct)
        print(f"#{decision_id} {symbol}: {action} {pct_change:+.2f}% -> {correct}")


if __name__ == "__main__":
    check_all()
