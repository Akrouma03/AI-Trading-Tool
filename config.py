import os

# Absolute paths so the scripts work no matter where they're run from (e.g. cron)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(PROJECT_DIR, "trades.db")
ENV_FILE = os.path.join(PROJECT_DIR, ".env")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3.8:27b"

# None = model default (varied answers). Set to 0.0 for deterministic output
# when running the "same input -> same decision?" consistency study.
TEMPERATURE = None

# No timeout means a stalled API or a wedged Ollama run hangs the job forever.
# A 27B model on CPU is genuinely slow, so it gets a much longer budget.
HTTP_TIMEOUT = 20
OLLAMA_TIMEOUT = 900

# Thinking is why the 27B model takes minutes per symbol rather than seconds.
# None = leave the model's own default, True = force on, False = force off
# (dramatically faster, at the cost of the reasoning trace this project studies).
THINKING = None

# Don't act on a coin-flip. Below this the decision is still logged (so the
# scoring loop keeps learning from it) but no order is sent.
MIN_CONFIDENCE = 0.6

# Binance testnet's own candle history is effectively empty (one daily bar),
# which fed the model a single price and a flat "0.00% change". Market data
# therefore comes from the public production endpoint (read-only, no key)
# while orders still execute against the testnet account.
BINANCE_DATA_URL = "https://api.binance.com/api/v3"
BINANCE_TRADE_URL = "https://testnet.binance.vision/api/v3"

# Refuse to ask for a decision on less history than this
MIN_BARS = 5

# Candle size for the crypto watch loop. Daily bars change once a day, so a
# 5-minute loop re-asked the model the identical question ~50 times in a row
# and traded on every repeat. Keep this and WATCH_INTERVAL_SECONDS in step.
CRYPTO_INTERVAL = "1h"

# 10 candles is too short a window to tell a trend from a spike -- every move
# looks like a local extreme, which pushed the model into fading every rally.
CRYPTO_BARS = 48
WATCH_INTERVAL_SECONDS = 3600

# Shorting is a deliberate part of this strategy, so this stays on. Be aware
# that a "sell" with no position opens a naked short with unbounded downside,
# and there is no stop-loss anywhere in the system: set this False to make the
# bot long-only, so a sell can only ever close an existing long.
ALLOW_SHORTS = True

# Roughly how much money each stock order should move. A flat qty=1 made every
# position a different size by accident -- one share of BAC is ~$62 of risk,
# one share of META ~$642.
TARGET_NOTIONAL = 200.0

CRYPTO_SYMBOLS = [
    "BTCUSDT",
    "ETHUSDT",
    "ZECUSDT",
    "PROMUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "NEARUSDT",
    "DOGEUSDT",
    "SUIUSDT",
    "HOLOUSDT",
    "UNIUSDT",
    "MARSCOINUSDT",
    "PUMPUSDT",
    "LINKUSDT",
    "ADAUSDT",
    "ENAUSDT",
    "TAOUSDT",
    "WLDUSDT",
    "IOSTUSDT",
    "DOTUSDT",
    "PEPEUSDT",
    "DASHUSDT",
    "SAHARAUSDT",
    "TRXUSDT",
]

SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "AVGO", "JPM",
    "V", "UNH", "XOM", "MA", "PG", "HD", "COST", "MRK", "ABBV", "CVX",
    "PEP", "KO", "ADBE", "WMT", "CRM", "BAC", "TMO", "MCD", "CSCO", "ACN",
    "NFLX", "ABT", "LIN", "DHR", "AMD", "TXN", "WFC", "PM", "NEE", "DIS",
    "VZ", "INTC", "CMCSA", "COP", "ORCL", "IBM", "AMGN", "UPS", "RTX", "HON",
]
