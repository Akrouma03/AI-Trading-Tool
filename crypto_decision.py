import json
from ollama_client import ask_ollama
from crypto_data import get_crypto_price, get_crypto_klines
from crypto_broker import place_crypto_order, get_asset_balance
from db import init_db, log_decision, log_order
from decision import parse_decision, describe_news
from news_data import get_market_news
from config import MODEL, CRYPTO_SYMBOLS


def base_asset(symbol):
    """BTCUSDT -> BTC. Assumes every pair is quoted in USDT."""
    return symbol.replace("USDT", "")


def get_news_safe():
    try:
        return get_market_news()
    except Exception as e:
        print(f"  (news fetch failed: {e})")
        return []


def build_prompt(symbol, bars, asset_balance, usdt_balance, headlines):
    closes = [bar["c"] for bar in bars]
    latest = closes[-1]
    change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
    base = base_asset(symbol)
    return f"""You are a crypto trading assistant. Symbol: {symbol} (trades 24/7).
Last {len(closes)} daily closes: {closes}
Latest close: {latest}
Change over this period: {change_pct:.2f}%
You currently hold {asset_balance} {base} and {usdt_balance:.2f} USDT available (this is spot trading: buy spends USDT to acquire {base}, sell converts {base} back to USDT, no shorting).
{describe_news(headlines)}
Decide: buy, sell, or hold, based on whether now is a good time to add to, trim, or leave your {base} position.
If the news is unrelated to why the price moved, say so rather than forcing a connection.
Also state what you expect to happen next as a concrete, checkable prediction (e.g. "price rises above 68000 within a few days"), not a vague statement.
Respond with ONLY valid JSON, no other text, in exactly this format:
{{"action": "buy|sell|hold", "confidence": 0.0-1.0, "reasoning": "...", "expected_outcome": "..."}}
"""


def get_crypto_decision(symbol, headlines):
    bars = get_crypto_klines(symbol)
    asset_balance = get_asset_balance(base_asset(symbol))
    usdt_balance = get_asset_balance("USDT")
    prompt = build_prompt(symbol, bars, asset_balance, usdt_balance, headlines)
    raw = ask_ollama(prompt)
    decision = parse_decision(raw)

    if decision["action"] == "sell" and asset_balance <= 0:
        decision["action"] = "hold"
        decision["reasoning"] += " (forced to hold: no balance to sell)"
    elif decision["action"] == "buy" and usdt_balance <= 0:
        decision["action"] = "hold"
        decision["reasoning"] += " (forced to hold: no USDT to buy with)"

    market_state = json.dumps({"bars": bars, "asset_balance": asset_balance, "usdt_balance": usdt_balance, "headlines": headlines})
    decision_id = log_decision(
        symbol,
        market_state,
        decision["action"],
        decision["confidence"],
        decision["reasoning"],
        MODEL,
        balance_at_decision=usdt_balance,
        expected_outcome=decision["expected_outcome"],
    )

    order = place_crypto_order(symbol, decision["action"])
    if order is not None:
        log_order(decision_id, order)

    order_note = "no order (hold)" if order is None else order.get("status") or order.get("reason", "?")
    print(f"{symbol}: {decision['action']} ({decision['confidence']}) usdt_balance={usdt_balance:.2f} -> {order_note}")
    print(f"  expects: {decision['expected_outcome']}")
    return decision


if __name__ == "__main__":
    init_db()
    headlines = get_news_safe()
    for symbol in CRYPTO_SYMBOLS:
        try:
            get_crypto_decision(symbol, headlines)
        except Exception as e:
            print(symbol, "FAILED:", e)
