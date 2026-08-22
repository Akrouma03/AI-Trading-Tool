import json
from ollama_client import ask_ollama
from crypto_data import get_crypto_price, get_crypto_klines
from crypto_broker import place_crypto_order, get_asset_balance
from db import init_db, log_decision, log_order
from decision import parse_decision
from config import MODEL, CRYPTO_SYMBOLS


def base_asset(symbol):
    """BTCUSDT -> BTC. Assumes every pair is quoted in USDT."""
    return symbol.replace("USDT", "")


def build_prompt(symbol, bars, balance):
    closes = [bar["c"] for bar in bars]
    latest = closes[-1]
    change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
    return f"""You are a crypto trading assistant. Symbol: {symbol} (trades 24/7).
Last {len(closes)} daily closes: {closes}
Latest close: {latest}
Change over this period: {change_pct:.2f}%
You currently hold {balance} {base_asset(symbol)} (this is spot trading: you can only sell what you already hold, no shorting).
Decide: buy, sell, or hold.
Respond with ONLY valid JSON, no other text, in exactly this format:
{{"action": "buy|sell|hold", "confidence": 0.0-1.0, "reasoning": "..."}}
"""


def get_crypto_decision(symbol):
    bars = get_crypto_klines(symbol)
    balance = get_asset_balance(base_asset(symbol))
    prompt = build_prompt(symbol, bars, balance)
    raw = ask_ollama(prompt)
    decision = parse_decision(raw)

    if decision["action"] == "sell" and balance <= 0:
        decision["action"] = "hold"
        decision["reasoning"] += " (forced to hold: no balance to sell)"

    market_state = json.dumps({"bars": bars, "balance": balance})
    decision_id = log_decision(
        symbol,
        market_state,
        decision["action"],
        decision["confidence"],
        decision["reasoning"],
        MODEL,
    )

    order = place_crypto_order(symbol, decision["action"])
    if order is not None:
        log_order(decision_id, order)

    order_note = "no order (hold)" if order is None else order.get("status") or order.get("reason", "?")
    print(f"{symbol}: {decision['action']} ({decision['confidence']}) -> {order_note}")
    return decision


if __name__ == "__main__":
    init_db()
    for symbol in CRYPTO_SYMBOLS:
        try:
            get_crypto_decision(symbol)
        except Exception as e:
            print(symbol, "FAILED:", e)
