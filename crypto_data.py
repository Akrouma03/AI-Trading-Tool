import requests

BASE_URL = "https://testnet.binance.vision/api/v3"


def get_crypto_price(symbol):
    url = f"{BASE_URL}/ticker/price"
    params = {"symbol": symbol}
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return float(data["price"])


def get_crypto_klines(symbol, limit=10):
    url = f"{BASE_URL}/klines"
    params = {"symbol": symbol, "interval": "1d", "limit": limit}
    response = requests.get(url, params=params)
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

if __name__ == "__main__":
    print(get_crypto_price("BTCUSDT"))
    print(get_crypto_klines("BTCUSDT")[-1])