import os
import requests
from dotenv import load_dotenv
from config import ENV_FILE, HTTP_TIMEOUT, ALLOW_SHORTS, TARGET_NOTIONAL

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
    response = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    return float(response.json()["equity"])


def get_position(symbol):
    """Current holding in this stock, or None if we hold nothing."""
    url = f"{BASE_URL}/v2/positions/{symbol}"
    response = requests.get(url, headers=HEADERS, timeout=HTTP_TIMEOUT)
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
    response = requests.get(url, headers=HEADERS, params={"status": "open", "symbols": symbol}, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    return len(response.json()) > 0


def order_qty(symbol, price=None):
    """Whole shares worth roughly TARGET_NOTIONAL, at least one."""
    from market_data import get_price

    price = price if price is not None else get_price(symbol)
    return max(1, int(TARGET_NOTIONAL // price))


def place_order(symbol, action, qty=None):
    if action == "hold":
        return None

    if has_open_order(symbol):
        return {"skipped": True, "reason": f"open order already pending for {symbol}"}

    side = "buy" if action == "buy" else "sell"

    position = get_position(symbol)
    held = position["qty"] if position else 0.0

    # Checked before sizing so an explicitly passed qty can't bypass it.
    if side == "sell" and held <= 0 and not ALLOW_SHORTS:
        return {"skipped": True, "reason": f"sell with no long {symbol} position would open/extend a short (ALLOW_SHORTS is off)"}

    if qty is None:
        if side == "sell" and held > 0:
            qty = int(held)  # closing a long: never sell more than we hold
        elif side == "buy" and held < 0:
            qty = int(abs(held))  # buying while short covers it rather than flipping long
        else:
            qty = order_qty(symbol)

    if qty < 1:
        return {"skipped": True, "reason": f"computed qty {qty} for {symbol} is below one whole share"}
    url = f"{BASE_URL}/v2/orders"
    payload = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    response = requests.post(url, headers=HEADERS, json=payload, timeout=HTTP_TIMEOUT)
    result = response.json()

    # Alpaca answers a rejected order with a JSON error body and a 4xx status.
    # Returning it unchanged logged it into the orders table as though it had
    # been placed, so failures looked identical to fills.
    if response.status_code >= 400 or "id" not in result:
        return {
            "skipped": True,
            "reason": f"order rejected ({response.status_code}): {result.get('message', result)}",
            "symbol": symbol,
            "side": side,
        }
    return result
