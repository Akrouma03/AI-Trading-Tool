"""Unit tests for the pure decision/scoring logic (no network, no DB)."""
import unittest
from datetime import datetime
from unittest import mock

import broker
from broker import order_qty

from decision import parse_decision, gate_by_confidence
from check_outcomes import (score, bar_time, reference_price, is_crypto,
                            meaningful_move, bars_per_horizon, MIN_MEANINGFUL_PCT)
from config import MIN_CONFIDENCE, TARGET_NOTIONAL

ANSWER = '{"action": "%s", "confidence": %s, "reasoning": "r", "expected_outcome": "e"}'


class TestParseDecision(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_decision(ANSWER % ("buy", 0.8))["action"], "buy")

    def test_ignores_braces_inside_thinking_block(self):
        raw = '<think>schema is {"action": "buy"}, but I lean hold</think>\n' + ANSWER % ("hold", 0.6)
        self.assertEqual(parse_decision(raw)["action"], "hold")

    def test_unterminated_thinking_block(self):
        raw = '<think>maybe {"action":"buy"} no\n' + ANSWER % ("sell", 0.9)
        with self.assertRaises(ValueError):
            parse_decision(raw)

    def test_markdown_fence_and_prose(self):
        raw = "Here is my call:\n```json\n" + ANSWER % ("sell", 0.4) + "\n```"
        self.assertEqual(parse_decision(raw)["action"], "sell")

    def test_braces_inside_a_string_value(self):
        raw = '{"action": "buy", "confidence": 0.7, "reasoning": "format {a:b}", "expected_outcome": "e"}'
        self.assertEqual(parse_decision(raw)["action"], "buy")

    def test_rejects_bad_action(self):
        with self.assertRaises(ValueError):
            parse_decision(ANSWER % ("yolo", 0.5))

    def test_rejects_out_of_range_confidence(self):
        with self.assertRaises(ValueError):
            parse_decision(ANSWER % ("buy", 1.7))

    def test_rejects_output_with_no_json(self):
        with self.assertRaises(ValueError):
            parse_decision("I would probably hold here.")


class TestConfidenceGate(unittest.TestCase):
    def test_low_confidence_trade_is_blocked(self):
        gate = gate_by_confidence({"action": "buy", "confidence": MIN_CONFIDENCE - 0.1})
        self.assertIsNotNone(gate)
        self.assertTrue(gate["skipped"])

    def test_confident_trade_passes(self):
        self.assertIsNone(gate_by_confidence({"action": "buy", "confidence": MIN_CONFIDENCE}))

    def test_hold_is_never_gated(self):
        self.assertIsNone(gate_by_confidence({"action": "hold", "confidence": 0.01}))


class TestScoring(unittest.TestCase):
    def test_buy_needs_a_real_rise(self):
        self.assertEqual(score("buy", 2.0, threshold=1.0), "yes")
        self.assertEqual(score("buy", 0.5, threshold=1.0), "no")

    def test_sell_needs_a_real_fall(self):
        self.assertEqual(score("sell", -2.0, threshold=1.0), "yes")
        self.assertEqual(score("sell", -0.5, threshold=1.0), "no")

    def test_hold_needs_quiet(self):
        self.assertEqual(score("hold", 0.5, threshold=1.0), "yes")
        self.assertEqual(score("hold", -3.0, threshold=1.0), "no")

    def test_same_move_scores_differently_by_asset_volatility(self):
        """A 2% move is real for a calm stock and noise for a volatile coin."""
        calm = [{"c": 100 + i * 0.1, "t": f"2026-08-{10 + i:02d}"} for i in range(10)]
        wild = [{"c": 100 * (1.08 ** (i % 2)), "t": f"2026-08-{10 + i:02d}"} for i in range(10)]
        self.assertEqual(score("buy", 2.0, meaningful_move(calm)), "yes")
        self.assertEqual(score("buy", 2.0, meaningful_move(wild)), "no")


class TestVolatilityThreshold(unittest.TestCase):
    def test_floor_applies_to_a_flat_series(self):
        flat = [{"c": 100.0, "t": f"2026-08-{10 + i:02d}"} for i in range(5)]
        self.assertEqual(meaningful_move(flat), MIN_MEANINGFUL_PCT)

    def test_horizon_scaling_reads_daily_bars(self):
        daily = [{"c": 100.0, "t": f"2026-08-{10 + i:02d}"} for i in range(5)]
        self.assertAlmostEqual(bars_per_horizon(daily), 3.0)

    def test_horizon_scaling_reads_hourly_bars(self):
        hour = 3600 * 1000
        hourly = [{"c": 100.0, "t": 1787356800000 + i * hour} for i in range(5)]
        self.assertAlmostEqual(bars_per_horizon(hourly), 72.0)

    def test_volatile_asset_gets_a_higher_bar(self):
        calm = [{"c": 100 + i * 0.1, "t": f"2026-08-{10 + i:02d}"} for i in range(10)]
        wild = [{"c": 100 * (1.08 ** (i % 2)), "t": f"2026-08-{10 + i:02d}"} for i in range(10)]
        self.assertGreater(meaningful_move(wild), meaningful_move(calm))


class TestOutcomeHelpers(unittest.TestCase):
    def test_binance_epoch_millis_bar(self):
        self.assertEqual(bar_time({"t": 1787356800000}).date(), datetime(2026, 8, 22).date())

    def test_alpaca_iso_string_bar(self):
        self.assertEqual(bar_time({"t": "2026-08-20T04:00:00Z"}).date(), datetime(2026, 8, 20).date())

    def test_recorded_price_wins_over_stale_close(self):
        self.assertEqual(reference_price(101.5, [{"c": 90.0}]), 101.5)

    def test_falls_back_to_close_for_legacy_rows(self):
        self.assertEqual(reference_price(None, [{"c": 90.0}]), 90.0)

    def test_market_routing(self):
        self.assertTrue(is_crypto("BTCUSDT"))
        self.assertFalse(is_crypto("AAPL"))


class TestOrderSizing(unittest.TestCase):
    def test_cheap_stock_gets_more_shares(self):
        self.assertEqual(order_qty("BAC", price=62.39), int(TARGET_NOTIONAL // 62.39))

    def test_expensive_stock_floors_at_one_share(self):
        self.assertEqual(order_qty("META", price=99999.0), 1)

    def test_sizes_are_closer_in_money_than_flat_qty_one(self):
        cheap, dear = 62.39, 613.36
        spread = (order_qty("A", cheap) * cheap) / (order_qty("B", dear) * dear)
        flat_spread = cheap / dear
        self.assertGreater(spread, flat_spread)


class TestShortProtection(unittest.TestCase):
    def _place(self, action, position, allow_shorts):
        with mock.patch.object(broker, "has_open_order", return_value=False), \
             mock.patch.object(broker, "get_position", return_value=position), \
             mock.patch.object(broker, "ALLOW_SHORTS", allow_shorts), \
             mock.patch.object(broker.requests, "post") as post:
            post.return_value = mock.Mock(status_code=200, **{"json.return_value": {"id": "x"}})
            return broker.place_order(action=action, symbol="AAPL", qty=1), post

    def test_sell_with_no_position_is_blocked(self):
        result, post = self._place("sell", None, allow_shorts=False)
        self.assertTrue(result["skipped"])
        post.assert_not_called()

    def test_sell_that_closes_a_long_is_allowed(self):
        result, post = self._place("sell", {"qty": 5.0}, allow_shorts=False)
        self.assertEqual(result["id"], "x")

    def test_short_allowed_when_explicitly_enabled(self):
        result, post = self._place("sell", None, allow_shorts=True)
        self.assertEqual(result["id"], "x")

    def test_rejected_order_is_not_recorded_as_filled(self):
        with mock.patch.object(broker, "has_open_order", return_value=False), \
             mock.patch.object(broker, "get_position", return_value=None), \
             mock.patch.object(broker.requests, "post") as post:
            post.return_value = mock.Mock(status_code=403, **{"json.return_value": {"message": "insufficient buying power"}})
            result = broker.place_order("AAPL", "buy", qty=1)
        self.assertTrue(result["skipped"])
        self.assertIn("insufficient buying power", result["reason"])


if __name__ == "__main__":
    unittest.main()
