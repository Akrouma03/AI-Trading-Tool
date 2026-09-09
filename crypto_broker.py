import os
import math
from decimal import Decimal, ROUND_DOWN
import uuid
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
    if not API_KEY or not SECRET_KEY:
        raise ValueError("Binance testnet credentials are missing")
    params = dict(params)
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


def place_crypto_order(symbol, action, quote_qty=50):
    """Size using the execution venue, never public-market prices."""
    if action not in ("buy", "sell", "hold"):
        raise ValueError("invalid action")
    if action == "hold":
        return None
    if not math.isfinite(quote_qty) or quote_qty <= 0:
        raise ValueError("order budget must be positive and finite")
    def skip(reason):
        return {"skipped": True, "reason": reason, "symbol": symbol, "side": action.upper()}
    if has_open_order(symbol):
        return skip("open order already pending")
    response = requests.get(f"{BASE_URL}/exchangeInfo", params={"symbol": symbol}, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    info = response.json()["symbols"][0]
    if info["status"] != "TRADING" or not info.get("isSpotTradingAllowed", False):
        return skip("pair is unavailable for spot trading")
    response = requests.get(f"{BASE_URL}/ticker/price", params={"symbol": symbol}, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    price = Decimal(response.json()["price"])
    if not price.is_finite() or price <= 0:
        raise ValueError("invalid execution price")
    filters = info["filters"]
    budget = Decimal(str(quote_qty))
    if action == "buy":
        budget = min(budget, Decimal(str(get_asset_balance(info["quoteAsset"]))) * Decimal("0.99"))
        quantity = budget / price
    else:
        quantity = min(budget / price, Decimal(str(get_asset_balance(info["baseAsset"]))))
    # Round down to both spot and market lot increments.
    steps = [Decimal(f["stepSize"]) for f in filters
             if f["filterType"] in ("LOT_SIZE", "MARKET_LOT_SIZE") and Decimal(f["stepSize"]) > 0]
    if steps:
        step = max(steps)
        quantity = (quantity / step).to_integral_value(rounding=ROUND_DOWN) * step
    if quantity <= 0:
        return skip("insufficient balance after lot rounding")
    for f in filters:
        kind = f["filterType"]
        if kind in ("LOT_SIZE", "MARKET_LOT_SIZE"):
            for key, below in (("minQty", True), ("maxQty", False)):
                bound = Decimal(f[key])
                if bound > 0 and ((quantity < bound) if below else (quantity > bound)):
                    return skip(f"quantity outside {kind} {key}")
            step = Decimal(f["stepSize"])
            if step > 0 and quantity % step:
                return skip("incompatible lot increments")
        if kind == "MIN_NOTIONAL" and f.get("applyToMarket", False):
            if quantity * price < Decimal(f["minNotional"]):
                return skip("below pair minimum order value")
        if kind == "NOTIONAL":
            if f.get("applyMinToMarket") and quantity * price < Decimal(f["minNotional"]):
                return skip("below pair minimum order value")
            if f.get("applyMaxToMarket") and quantity * price > Decimal(f["maxNotional"]):
                return skip("above pair maximum order value")
    params = {"symbol": symbol, "side": action.upper(), "type": "MARKET",
              "quantity": format(quantity, "f"), "newClientOrderId": "local-" + uuid.uuid4().hex[:24]}
    try:
        response = signed_request("POST", "/order", params)
    except requests.RequestException:
        return {"status": "UNKNOWN", "symbol": symbol, "side": action.upper(),
                "reason": "Order submission uncertain; check exchange before retrying",
                "clientOrderId": params["newClientOrderId"]}
    try:
        result = response.json()
    except ValueError:
        return {"status": "UNKNOWN", "symbol": symbol, "clientOrderId": params["newClientOrderId"]}
    if response.status_code >= 500:
        return {"status": "UNKNOWN", "symbol": symbol, "clientOrderId": params["newClientOrderId"], "raw": result}
    if response.status_code >= 400 or "code" in result:
        return skip(f"exchange rejected order: {result.get('msg', result)}")
    return result


if __name__ == "__main__":
    print("USDT balance:", get_asset_balance("USDT"))
    print("BTC balance:", get_asset_balance("BTC"))
