# Running the local paper trader

Run `./venv/bin/python watch_crypto.py` from this directory. The model remains
`qwen3.8:27b` served by local Ollama. Binance orders still use testnet and Alpaca
orders still use its paper account. The watcher prints progress, runs the configured
24 symbols sequentially, and grades eligible new decisions after each pass.
Ctrl+C stops it. Nothing runs while Linux is shut down.

## Repairs

- Imported the missing CRYPTO_BARS setting; preserved the existing 48-bar change.
- Use completed hourly candles, reject missing/stale data, and pass the same snapshot
  to the prompt rather than fetching a different one after deduplication.
- Remember processed candles across restarts; lock against simultaneous watchers.
- Keep model proposals unchanged when an account cannot execute them. Log skips separately.
- Reject malformed, ambiguous or unfinished model responses and invalid prices.
- Capture the reference price after inference, matching the logged decision time.
- Keep Qwen loaded for two hours to reduce reloads between passes.
- Size crypto orders against testnet prices and balances, rounding down to pair lot
  increments and checking market notional restrictions. Exchange remains final authority.
- Unknown submissions are logged and block further orders for that symbol until
  manually reconciled with the exchange. No automatic retry of order POST requests.
- Explicit stock quantities cannot oversell an existing long or over-cover a short.
- Grade new records separately in evaluations_v2. Old outcomes are preserved.

## What results mean

The earlier 15% claim was not a reliable model-performance estimate. Old records mix
scoring methods, duplicated inputs, and testnet/public price sources. No old records
are deleted or relabelled by these repairs.

New scores measure direction against the close of the first daily candle beginning
on/after the 72-hour target (next available session for stocks). They wait for that
candle to finish; grading can take longer than three days. This is not exact 72-hour
P/L and does not evaluate arbitrary price targets inside model prose. No live-price
fallback is allowed when history is missing. Threshold and candle time are stored.
Confidence is a model-provided number, not a calibrated probability. More coins are
not independent observations. These changes do not establish trading profitability.

Tests use mocked services and temporary databases. No trades or live model inference
were executed during this repair pass. A crash between exchange submission and local
logging still requires checking the exchange; this is not an exactly-once transaction
system. Run only one trading entry point at a time.

Pair rules reference: https://developers.binance.com/docs/binance-spot-api-docs/filters
