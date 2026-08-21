import json
import sqlite3
from datetime import datetime
from market_data import get_price
from db import init_db, log_outcome
from config import DB_FILE

# Only score decisions at least this old (a 10-day-trend call needs time to play out).
MIN_AGE = "-1 day"

# If the newest bar the model saw was this much older than the decision itself,
# the input data was stale (early bug) and the outcome can't be trusted.
MAX_BAR_LAG_DAYS = 5


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

        if action == "buy":
            correct = "yes" if pct_change > 0 else "no"
        elif action == "sell":
            correct = "yes" if pct_change < 0 else "no"
        else:
            correct = "yes" if abs(pct_change) < 1 else "no"

        log_outcome(decision_id, price_at_decision, price_now, pct_change, correct)
        print(f"#{decision_id} {symbol}: {action} {pct_change:+.2f}% -> {correct}")


if __name__ == "__main__":
    check_all()
