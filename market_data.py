import os
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from config import ENV_FILE, HTTP_TIMEOUT

load_dotenv(ENV_FILE)

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY,
}


def get_price(symbol):
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest"
    response = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data["trade"]["p"]


def get_bars(symbol, limit=10):
    start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    params = {"timeframe": "1Day", "limit": 100, "start": start}
    response = requests.get(url, headers=HEADERS, params=params, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return data["bars"][-limit:]


def get_bar_after(symbol, start_date, limit=1):
    """First daily bar at or after start_date (YYYY-MM-DD), or None."""
    url = f"https://data.alpaca.markets/v2/stocks/{symbol}/bars"
    params = {"timeframe": "1Day", "limit": limit, "start": start_date}
    response = requests.get(url, headers=HEADERS, params=params, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    bars = response.json().get("bars") or []
    return bars[0] if bars else None


if __name__ == "__main__":
    print(get_price("AAPL"))
    print(get_bars("AAPL")[-1])
