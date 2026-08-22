import os
import requests
from dotenv import load_dotenv
from config import ENV_FILE

load_dotenv(ENV_FILE)

API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"

HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY,
}


def get_account_balance():
    """Total portfolio equity right now (cash + all positions)."""
    url = f"{BASE_URL}/v2/account"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return float(response.json()["equity"])


def get_position(symbol):
    """Current holding in this stock, or None if we hold nothing."""
    url = f"{BASE_URL}/v2/positions/{symbol}"
    response = requests.get(url, headers=HEADERS)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    p = response.json()
    return {
        "qty": float(p["qty"]),
        "avg_entry_price": float(p["avg_entry_price"]),
        "unrealized_pl": float(p["unrealized_pl"]),
    }


def has_open_order(symbol):
    """True if an unfilled order for this stock is already waiting."""
    url = f"{BASE_URL}/v2/orders"
    response = requests.get(url, headers=HEADERS, params={"status": "open", "symbols": symbol})
    response.raise_for_status()
    return len(response.json()) > 0


def place_order(symbol, action, qty=1):
    if action == "hold":
        return None

    if has_open_order(symbol):
        return {"skipped": True, "reason": f"open order already pending for {symbol}"}

    side = "buy" if action == "buy" else "sell"
    url = f"{BASE_URL}/v2/orders"
    payload = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    response = requests.post(url, headers=HEADERS, json=payload)
    return response.json()
