import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from config import ENV_FILE

load_dotenv(ENV_FILE)

API_KEY = os.getenv("FINNHUB_API_KEY")
BASE_URL = "https://finnhub.io/api/v1"


def get_company_news(symbol, days=3, limit=5):
    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = f"{BASE_URL}/company-news"
    params = {"symbol": symbol, "from": from_date, "to": to_date, "token": API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    articles = response.json()
    headlines = [a["headline"] for a in articles[:limit]]
    return headlines


def get_market_news(limit=5):
    url = f"{BASE_URL}/news"
    params = {"category": "general", "token": API_KEY}
    response = requests.get(url, params=params)
    response.raise_for_status()
    articles = response.json()
    headlines = [a["headline"] for a in articles[:limit]]
    return headlines


if __name__ == "__main__":
    print("AAPL news:", get_company_news("AAPL"))
    print("Market news:", get_market_news())