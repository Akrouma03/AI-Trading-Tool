import json
import re
from ollama_client import generate
from market_data import get_bars, get_price
from db import init_db, log_decision, log_order
from broker import place_order, get_position, get_account_balance
from news_data import get_company_news
from config import SYMBOLS, MIN_CONFIDENCE, MIN_BARS


def get_news_safe(symbol):
    """News is a nice-to-have; never let a Finnhub hiccup kill a whole run."""
    try:
        return get_company_news(symbol)
    except Exception as e:
        print(f"  (news fetch failed for {symbol}: {e})")
        return []


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


def describe_news(headlines):
    if not headlines:
        return "No recent news found for this symbol."
    return "Recent headlines:\n" + "\n".join(f"- {h}" for h in headlines)


def require_history(symbol, bars):
    """A thin feed silently becomes a flat 0.00% trend, which reads as 'hold'.

    Better to skip the symbol loudly than to log a confident-looking decision
    the model made with no trend to look at.
    """
    if len(bars) < MIN_BARS:
        raise ValueError(f"only {len(bars)} bar(s) for {symbol}, need {MIN_BARS}")


def build_prompt(symbol, bars, position, headlines):
    require_history(symbol, bars)
    closes = [bar["c"] for bar in bars]
    latest = closes[-1]
    change_pct = ((closes[-1] - closes[0]) / closes[0]) * 100
    return f"""You are a trading assistant. Symbol: {symbol}.
Last {len(closes)} daily closes: {closes}
Latest close: {latest}
Change over this period: {change_pct:.2f}%
{describe_position(position)}
{describe_news(headlines)}
Decide: buy, sell, or hold. Note: buy while short closes/covers the short; sell while long closes the long; sell with no position opens a short.
If the news is unrelated to why the price moved, say so rather than forcing a connection.
Also state what you expect to happen next as a concrete, checkable prediction (e.g. "price rises above 315 within a few days"), not a vague statement.
Respond with ONLY valid JSON, no other text, in exactly this format:
{{"action": "buy|sell|hold", "confidence": 0.0-1.0, "reasoning": "...", "expected_outcome": "..."}}
"""


THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def iter_json_objects(text):
    r"""Yield each balanced {...} span in text, in the order they start.

    A greedy r"\{.*\}" runs from the first brace to the last one, so the
    moment the model writes a brace while reasoning the captured span is
    two fragments glued together and json.loads chokes on it.
    """
    depth = 0
    start = None
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth > 0:
            depth -= 1
            if depth == 0:
                yield text[start : i + 1]


def extract_decision_json(raw):
    """Pull the answer object out of model output that may carry reasoning.

    The configured model is a thinking model, so the real answer is the last
    decision-shaped object, not the first brace on the page.
    """
    for text in (THINK_BLOCK.sub("", raw), raw):
        for candidate in reversed(list(iter_json_objects(text))):
            try:
                obj = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "action" in obj:
                return obj
    raise ValueError(f"no decision JSON in model output: {raw[:200]!r}")


def parse_decision(raw):
    decision = extract_decision_json(raw)
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


def gate_by_confidence(decision):
    """Log every decision, but only trade the ones the model is actually sure of.

    Confidence was recorded and then ignored, so a 0.15 'buy' moved exactly as
    much money as a 0.95 one.
    """
    if decision["action"] == "hold" or decision["confidence"] >= MIN_CONFIDENCE:
        return None
    return {
        "skipped": True,
        "reason": f"confidence {decision['confidence']} below {MIN_CONFIDENCE} threshold",
    }


def get_decision(symbol):
    bars = get_bars(symbol)
    position = get_position(symbol)
    balance = get_account_balance()
    headlines = get_news_safe(symbol)
    prompt = build_prompt(symbol, bars, position, headlines)
    result = generate(prompt)
    raw, thinking = result["response"], result["thinking"]
    decision = parse_decision(raw)

    # The live price the decision was actually made at. Scoring against the
    # last daily close instead credits the model for moves it never saw.
    price_at_decision = get_price(symbol)

    market_state = json.dumps({"bars": bars, "position": position, "headlines": headlines})
    decision_id = log_decision(
        symbol,
        market_state,
        decision["action"],
        decision["confidence"],
        decision["reasoning"],
        result["model"],
        balance_at_decision=balance,
        expected_outcome=decision["expected_outcome"],
        price_at_decision=price_at_decision,
        thinking=thinking,
    )

    order = gate_by_confidence(decision) or place_order(symbol, decision["action"])
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
