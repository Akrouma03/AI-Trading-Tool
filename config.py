import os

# Absolute paths so the scripts work no matter where they're run from (e.g. cron)
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(PROJECT_DIR, "trades.db")
ENV_FILE = os.path.join(PROJECT_DIR, ".env")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3:8b"

# None = model default (varied answers). Set to 0.0 for deterministic output
# when running the "same input -> same decision?" consistency study.
TEMPERATURE = None

SYMBOLS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B", "AVGO", "JPM",
    "V", "UNH", "XOM", "MA", "PG", "HD", "COST", "MRK", "ABBV", "CVX",
    "PEP", "KO", "ADBE", "WMT", "CRM", "BAC", "TMO", "MCD", "CSCO", "ACN",
    "NFLX", "ABT", "LIN", "DHR", "AMD", "TXN", "WFC", "PM", "NEE", "DIS",
    "VZ", "INTC", "CMCSA", "COP", "ORCL", "IBM", "AMGN", "UPS", "RTX", "HON",
]
