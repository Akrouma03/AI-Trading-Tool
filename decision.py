import json
import re
from ollama_client import ask_ollama
from market_data import get_bars
from db import init_db, log_decision, log_order
from broker import place_order, get_position, get_account_balance
from config import MODEL, SYMBOLS


def describe_position(position):
    if position is None:
        return "You currently hold no position in this stock."
    if position["qty"] > 0:
        return (
            f"You are LONG {position['qty']:g} share(s), entered at "
            f"{position['avg_entry_price']}, unrealized P/L {position['unrealized_pl']:+.2f}."
        )
    return (
        f"You are SHORT {abs(position['qty']):g} share(s), entered at "
        f"{position['avg_entry_price']}, unrealized P/L {position['unrealized_pl']:+.2f}."
    )


def build_prompt(symbol, bars, position):
    closes = [bar["c"] for bar in bars]
    latest = closes[-1]
    change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
    return f"""You are a trading assistant. Symbol: {symbol}.
Last {len(closes)} daily closes: {closes}
Latest close: {latest}
Change over this period: {change_pct:.2f}%
{describe_position(position)}
Decide: buy, sell, or hold. Note: buy while short closes/covers the short; sell while long closes the long; sell with no position opens a short.
Also state what you expect to happen next as a concrete, checkable prediction (e.g. "price rises above 315 within a few days"), not a vague statement.
Respond with ONLY valid JSON, no other text, in exactly this format:
{{"action": "buy|sell|hold", "confidence": 0.0-1.0, "reasoning": "...", "expected_outcome": "..."}}
"""


def parse_decision(raw):
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match is None:
        raise ValueError(f"no JSON object in model output: {raw[:200]!r}")
    decision = json.loads(match.group(0))
    action = str(decision.get("action", "")).strip().lower()
    if action not in ("buy", "sell", "hold"):
        raise ValueError(f"invalid action: {action!r}")
    confidence = float(decision.get("confidence", -1))
    if not 0.0 <= confidence <= 1.0:
        raise ValueError(f"confidence out of range: {confidence}")
    return {
        "action": action,
        "confidence": confidence,
        "reasoning": str(decision.get("reasoning", "")),
        "expected_outcome": str(decision.get("expected_outcome", "")),
    }


def get_decision(symbol):
    bars = get_bars(symbol)
    position = get_position(symbol)
    balance = get_account_balance()
    prompt = build_prompt(symbol, bars, position)
    raw = ask_ollama(prompt)
    decision = parse_decision(raw)

    market_state = json.dumps({"bars": bars, "position": position})
    decision_id = log_decision(
        symbol,
        market_state,
        decision["action"],
        decision["confidence"],
        decision["reasoning"],
        MODEL,
        balance_at_decision=balance,
        expected_outcome=decision["expected_outcome"],
    )

    order = place_order(symbol, decision["action"])
    if order is not None:
        log_order(decision_id, order)

    order_note = "no order (hold)" if order is None else order.get("status") or order.get("reason", "?")
    print(f"{symbol}: {decision['action']} ({decision['confidence']}) balance={balance:.2f} -> {order_note}")
    print(f"  expects: {decision['expected_outcome']}")
    return decision


if __name__ == "__main__":
    init_db()
    for symbol in SYMBOLS:
        try:
            get_decision(symbol)
        except Exception as e:
            print(symbol, "FAILED:", e)
