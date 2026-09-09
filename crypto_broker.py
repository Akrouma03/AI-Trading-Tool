import os
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv
from urllib.parse import urlencode
from config import ENV_FILE, HTTP_TIMEOUT, BINANCE_TRADE_URL
from crypto_data import get_crypto_price

load_dotenv(ENV_FILE)

API_KEY = os.getenv("BINANCE_API_KEY")
SECRET_KEY = os.getenv("BINANCE_SECRET_KEY")
BASE_URL = BINANCE_TRADE_URL  # orders stay on the paper-trading testnet

HEADERS = {"X-MBX-APIKEY": API_KEY}


def signed_request(method, path, params):
    params["timestamp"] = int(time.time() * 1000)
    query_string = urlencode(params)
    signature = hmac.new(
        SECRET_KEY.encode(),
        query_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    params["signature"] = signature

    url = f"{BASE_URL}{path}"
    response = requests.request(method, url, headers=HEADERS, params=params, timeout=HTTP_TIMEOUT)
    return response


def get_asset_balance(asset):
    response = signed_request("GET", "/account", {})
    response.raise_for_status()
    for b in response.json()["balances"]:
        if b["asset"] == asset:
            return float(b["free"])
    return 0.0


def has_open_order(symbol):
    response = signed_request("GET", "/openOrders", {"symbol": symbol})
    response.raise_for_status()
    return len(response.json()) > 0


MIN_NOTIONAL = 10.0


def place_crypto_order(symbol, action, quote_qty=50):
    """quote_qty = how much USDT worth to trade, not a coin count."""
    if action == "hold":
        return None

    if has_open_order(symbol):
        return {"skipped": True, "reason": f"open order already pending for {symbol}"}

    side = "BUY" if action == "buy" else "SELL"

    if side == "SELL":
        base_asset = symbol.replace("USDT", "")
        free = get_asset_balance(base_asset)
        price = get_crypto_price(symbol)
        # cap the sell at what we actually hold, leaving a small margin for
        # price drift between this check and order execution
        quote_qty = min(quote_qty, free * price * 0.999)
        if quote_qty < MIN_NOTIONAL:
            return {"skipped": True, "reason": f"{base_asset} holding worth {quote_qty:.2f} USDT is below the {MIN_NOTIONAL} minimum"}
    else:
        usdt_free = get_asset_balance("USDT")
        quote_qty = min(quote_qty, usdt_free * 0.999)
        if quote_qty < MIN_NOTIONAL:
            return {"skipped": True, "reason": f"{quote_qty:.2f} USDT free is below the {MIN_NOTIONAL} minimum"}

    # Binance rejects quoteOrderQty with more precision than the quote asset allows
    quote_qty = round(quote_qty, 2)

    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "quoteOrderQty": quote_qty,
    }
    response = signed_request("POST", "/order", params)
    result = response.json()

    # A Binance rejection is a 4xx with {"code": -2010, "msg": ...}. Passing it
    # straight through wrote error bodies into the orders table as real orders.
    if response.status_code >= 400 or "code" in result:
        return {
            "skipped": True,
            "reason": f"order rejected ({result.get('code')}): {result.get('msg', result)}",
            "symbol": symbol,
            "side": side,
        }
    return result


if __name__ == "__main__":
    print("USDT balance:", get_asset_balance("USDT"))
    print("BTC balance:", get_asset_balance("BTC"))
