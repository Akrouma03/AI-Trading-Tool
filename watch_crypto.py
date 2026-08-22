import time
from datetime import datetime
from db import init_db
from crypto_decision import get_crypto_decision, get_news_safe
from config import CRYPTO_SYMBOLS

INTERVAL_SECONDS = 300  # 5 minutes between passes


def run_pass():
    print(f"\n=== pass at {datetime.now().strftime('%H:%M:%S')} ===")
    headlines = get_news_safe()
    for symbol in CRYPTO_SYMBOLS:
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
