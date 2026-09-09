"""Run the local model hourly; a lock prevents two loops trading together."""
import fcntl
import json
import time
from pathlib import Path
from datetime import datetime
from db import init_db, connect
from check_outcomes import check_all
from crypto_decision import get_crypto_decision, get_news_safe
from crypto_data import get_crypto_klines
from config import CRYPTO_SYMBOLS, WATCH_INTERVAL_SECONDS, CRYPTO_BARS, PROJECT_DIR

INTERVAL_SECONDS = WATCH_INTERVAL_SECONDS
_last_bar = {}


def load_last_bars():
    with connect() as conn:
        rows = conn.execute("SELECT symbol, market_state FROM decisions ORDER BY id").fetchall()
    for symbol, raw in rows:
        try:
            state = json.loads(raw)
            if isinstance(state, dict) and state.get('evaluation_version') == 'direction-v2':
                _last_bar[symbol] = state['bars'][-1]['t']
        except (ValueError, KeyError, IndexError, TypeError):
            continue


def run_pass():
    print(f"\n=== pass at {datetime.now():%H:%M:%S} ===", flush=True)
    headlines = get_news_safe()
    for index, symbol in enumerate(CRYPTO_SYMBOLS, 1):
        try:
            bars = get_crypto_klines(symbol, limit=CRYPTO_BARS)
            if not bars:
                raise ValueError('no completed candles')
            if time.time() * 1000 - bars[-1]['t'] > 3 * 3600 * 1000:
                raise ValueError('stale hourly candles')
            if _last_bar.get(symbol) == bars[-1]['t']:
                print(f'{symbol}: already processed this candle', flush=True)
                continue
            print(f'[{index}/{len(CRYPTO_SYMBOLS)}] {symbol}', flush=True)
            get_crypto_decision(symbol, headlines, bars=bars)
            _last_bar[symbol] = bars[-1]['t']
        except Exception as exc:
            print(f'{symbol}: FAILED ({type(exc).__name__}: {exc})', flush=True)


def main():
    with open(Path(PROJECT_DIR) / '.watch_crypto.lock', 'w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit('Another crypto watcher is already running.')
        init_db()
        load_last_bars()
        print(f'Watching {len(CRYPTO_SYMBOLS)} coins with local Qwen. Ctrl+C stops.', flush=True)
        try:
            while True:
                started = time.monotonic()
                run_pass()
                try:
                    check_all()
                except Exception as exc:
                    print(f"Grading failed: {exc}", flush=True)
                remaining = max(0, INTERVAL_SECONDS - (time.monotonic() - started))
                print(f'Pass finished; next pass in {remaining / 60:.0f} minutes.', flush=True)
                time.sleep(remaining)
        except KeyboardInterrupt:
            print('\nStopped. Results are saved.', flush=True)


if __name__ == '__main__':
    main()
