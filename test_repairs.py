import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import patch, Mock
import requests
import db
import decision
import crypto_data
import crypto_decision
import crypto_broker
import check_outcomes
import watch_crypto


class Repairs(unittest.TestCase):
    def test_rejects_ambiguous_and_invalid_decisions(self):
        valid = dict(action='buy', confidence=.7, reasoning='r', expected_outcome='e')
        for raw in (json.dumps(valid) * 2, json.dumps(dict(valid, confidence=True)),
                    json.dumps(dict(valid, reasoning='')), '<think>' + json.dumps(valid)):
            with self.assertRaises(ValueError):
                decision.parse_decision(raw)

    def test_closed_candles_only(self):
        response = Mock()
        response.json.return_value = [[1, '1', '2', '1', '2', '3', 100],
                                      [101, '2', '3', '2', '3', '4', 2000]]
        with patch.object(crypto_data.requests, 'get', return_value=response), patch.object(crypto_data.time, 'time', return_value=1):
            self.assertEqual(len(crypto_data.get_crypto_klines('BTCUSDT')), 1)

    def test_missing_horizon_never_uses_live_price(self):
        with patch.object(check_outcomes, 'get_kline_after', return_value=None), patch.object(check_outcomes, 'current_price') as live:
            with self.assertRaises(ValueError):
                check_outcomes.horizon_price('BTCUSDT', datetime(2020, 1, 1))
            live.assert_not_called()

    def test_future_horizon_is_pending(self):
        with self.assertRaises(ValueError):
            check_outcomes.horizon_price('BTCUSDT', datetime.now())

    def test_full_crypto_path_preserves_original_sell(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(db, 'DB_FILE', str(Path(tmp)/'test.db')):
            db.init_db()
            bars = [{'t': i*3600000, 'c': 100+i} for i in range(48)]
            result = {'response': json.dumps(dict(action='sell', confidence=.8, reasoning='r', expected_outcome='e')), 'thinking': 'trace', 'model': 'qwen3.8:27b'}
            with patch.object(crypto_decision, 'get_crypto_price', return_value=150), patch.object(crypto_decision, 'get_asset_balance', return_value=0), patch.object(crypto_decision, 'generate', return_value=result), patch.object(crypto_decision, 'place_crypto_order', return_value={'skipped': True, 'reason': 'no balance'}):
                crypto_decision.get_crypto_decision('BTCUSDT', [], bars=bars)
            with db.connect() as conn:
                self.assertEqual(conn.execute('SELECT action, thinking FROM decisions').fetchone(), ('sell', 'trace'))
            watch_crypto._last_bar.clear()
            watch_crypto.load_last_bars()
            self.assertEqual(watch_crypto._last_bar['BTCUSDT'], bars[-1]['t'])
            watch_crypto._last_bar.clear()

    def test_failed_pass_can_retry(self):
        bars = [{'t': int(__import__('time').time()*1000), 'c': 1}]
        with patch.object(watch_crypto, 'CRYPTO_SYMBOLS', ['TESTUSDT']), patch.object(watch_crypto, 'get_news_safe', return_value=[]), patch.object(watch_crypto, 'get_crypto_klines', return_value=bars), patch.object(watch_crypto, 'get_crypto_decision', side_effect=ValueError('bad reply')):
            watch_crypto.run_pass()
            self.assertNotIn('TESTUSDT', watch_crypto._last_bar)

    def test_sell_rounds_down_to_execution_lot(self):
        info = Mock()
        info.json.return_value = {'symbols': [{'status':'TRADING','isSpotTradingAllowed':True,'baseAsset':'BNB','quoteAsset':'USDT','filters':[{'filterType':'LOT_SIZE','minQty':'.001','maxQty':'1000','stepSize':'.001'}]}]}
        price = Mock()
        price.json.return_value = {'price':'700'}
        response = Mock(status_code=200)
        response.json.return_value = {'orderId': 1, 'status':'FILLED'}
        with patch.object(crypto_broker, 'has_open_order', return_value=False), patch.object(crypto_broker.requests, 'get', side_effect=[info, price]), patch.object(crypto_broker, 'get_asset_balance', return_value=.0678), patch.object(crypto_broker, 'signed_request', return_value=response) as submit:
            crypto_broker.place_crypto_order('BNBUSDT', 'sell')
            self.assertEqual(submit.call_args.args[2]['quantity'], '0.067')

    def test_order_timeout_is_unknown_and_not_retried(self):
        info = Mock()
        info.json.return_value = {'symbols': [{'status':'TRADING','isSpotTradingAllowed':True,'baseAsset':'BNB','quoteAsset':'USDT','filters':[]}]}
        price = Mock()
        price.json.return_value = {'price':'700'}
        with patch.object(crypto_broker, 'has_open_order', return_value=False), patch.object(crypto_broker.requests, 'get', side_effect=[info, price]), patch.object(crypto_broker, 'get_asset_balance', return_value=1000), patch.object(crypto_broker, 'signed_request', side_effect=requests.Timeout) as submit:
            result = crypto_broker.place_crypto_order('BNBUSDT', 'buy')
            self.assertEqual(result['status'], 'UNKNOWN')
            self.assertEqual(submit.call_count, 1)

    def test_evaluation_is_versioned_and_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(db, 'DB_FILE', str(Path(tmp)/'test.db')):
            db.init_db()
            bars = [{'t': f'2020-01-{i:02d}', 'c':100} for i in range(1, 11)]
            did = db.log_decision('BTCUSDT', json.dumps({'bars':bars, 'evaluation_version':'direction-v2'}), 'buy', .7, 'r', 'qwen3.8:27b', price_at_decision=100)
            with db.connect() as conn:
                conn.execute("UPDATE decisions SET timestamp='2020-01-10 12:00:00'")
            with patch.object(check_outcomes, 'horizon_price', return_value=(105, '2020-01-14')):
                check_outcomes.check_all()
                check_outcomes.check_all()
            with db.connect() as conn:
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM evaluations_v2').fetchone()[0], 1)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM outcomes').fetchone()[0], 0)

    def test_iso_time_not_truncated(self):
        self.assertEqual(check_outcomes.bar_time({'t':'2026-09-09T12:30:00Z'}).hour, 12)

    def test_invalid_prices_rejected(self):
        for price in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                decision.require_history('BTC', [{'c':price}]*5)

if __name__ == '__main__':
    unittest.main()
