import requests
from config import HTTP_TIMEOUT, BINANCE_DATA_URL, CRYPTO_INTERVAL

BASE_URL = BINANCE_DATA_URL


def get_crypto_price(symbol):
    url = f"{BASE_URL}/ticker/price"
    params = {"symbol": symbol}
    response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    return float(data["price"])


def get_crypto_klines(symbol, limit=10, interval=CRYPTO_INTERVAL):
    url = f"{BASE_URL}/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    raw = response.json()
    bars = []
    for k in raw:
        bars.append({
            "t": k[0],
            "o": float(k[1]),
            "h": float(k[2]),
            "l": float(k[3]),
            "c": float(k[4]),
            "v": float(k[5]),
        })
    return bars

def get_kline_after(symbol, start_ms, limit=1):
    """First daily kline at or after start_ms (epoch milliseconds), or None."""
    url = f"{BASE_URL}/klines"
    params = {"symbol": symbol, "interval": "1d", "limit": limit, "startTime": int(start_ms)}
    response = requests.get(url, params=params, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    raw = response.json()
    if not raw:
        return None
    k = raw[0]
    return {"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5])}


if __name__ == "__main__":
    print(get_crypto_price("BTCUSDT"))
    print(get_crypto_klines("BTCUSDT")[-1])