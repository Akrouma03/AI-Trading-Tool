import time
from datetime import datetime
from db import init_db
from crypto_decision import get_crypto_decision, get_news_safe
from crypto_data import get_crypto_klines
from config import CRYPTO_SYMBOLS, WATCH_INTERVAL_SECONDS

INTERVAL_SECONDS = WATCH_INTERVAL_SECONDS

# Last candle each symbol was decided on, so an unchanged market doesn't get
# re-decided (and re-traded) on every pass.
_last_bar = {}


def has_new_data(symbol):
    try:
        bars = get_crypto_klines(symbol)
    except Exception as e:
        print(f"  ({symbol} data fetch failed: {e})")
        return False
    latest = bars[-1]["t"]
    if _last_bar.get(symbol) == latest:
        return False
    _last_bar[symbol] = latest
    return True


def run_pass():
    print(f"\n=== pass at {datetime.now().strftime('%H:%M:%S')} ===")
    headlines = get_news_safe()
    for symbol in CRYPTO_SYMBOLS:
        if not has_new_data(symbol):
            print(f"{symbol}: unchanged since last pass, skipping")
            continue
        try:
            get_crypto_decision(symbol, headlines)
        except Exception as e:
            print(symbol, "FAILED:", e)


if __name__ == "__main__":
    init_db()
    print(f"Watching {CRYPTO_SYMBOLS} every {INTERVAL_SECONDS}s. Press Ctrl+C to stop.")
    try:
        while True:
            run_pass()
            time.sleep(INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopped by you. All decisions made so far are saved in trades.db.")
