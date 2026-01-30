# Discussion 6: CASH and CRYPTO Trade Processing

**Date**: 2026-01-29
**Status**: Applied and validated

## Problem

The tool skipped 83 trades (31 CASH/FX conversions, 52 CRYPTO) with an early return in `_process_trade`. These trades were excluded from the trial balance entirely, meaning FX conversion gains/losses and crypto gains/losses were not captured. For tax purposes (Corporation Tax), HMRC requires all chargeable gains and allowable losses to be reported.

## Decision

Remove the skip. Process all asset classes through the same FIFO machinery. Route gains/losses to the appropriate P&L accounts by asset class:

- **CASH** (FX conversions): gains to 4300 (Foreign Exchange Gains), losses to 5500 (Foreign Exchange Losses)
- **CRYPTO**: gains to 4200 (Realized Gains on Investments), losses to 5400 (Realized Losses on Investments) -- same as STK/OPT

All asset classes use account 1200 for cost tracking and 1101 for cash, consistent with existing logic.

## Alternative Considered

Processing CASH trades as cash movements between currency accounts (1100 GBP / 1101 USD / 1102 Other) rather than through FIFO. This would be more accurate for trial balance presentation but adds complexity and is not required for tax gain/loss reporting. Deferred to a future enhancement.

## Code Changes

`scripts/ibkr_trial_balance.py`:

1. Replaced the `if trade.asset_class in ('CASH', 'CRYPTO'): return` early exit with gain/loss account selection logic based on asset class
2. Changed hardcoded `'4200'`/`'5400'` references in the sell branch to use the selected `gain_account`/`loss_account` variables
3. Removed the "Skipping N trades" console message from `main()`

## Results

Before (STK+OPT only, 3905 trades processed):
- 4200 Realized Gains: part of net 377,533.11
- 5400 Realized Losses: part of net 377,533.11
- 4300 FX Gains: 0
- 5500 FX Losses: 0

After (all 3988 trades processed):
- 4200 Realized Gains: 1,014,206.86 (STK+OPT+CRYPTO)
- 5400 Realized Losses: 637,469.60 (STK+OPT+CRYPTO)
- Net investment P/L: 376,737.26
- 4300 FX Gains: 30,700.29 (CASH trades)
- 5500 FX Losses: 1.49 (CASH trades)
- Net FX P/L: 30,698.80
- Trial balance: balanced (DR = CR = 32,876,599.79)

Net investment P/L moved from 377,533.11 to 376,737.26 -- the 795.85 difference is the net impact of 52 crypto trades (small net loss).

## Known Limitations

- Account 1200 ("Listed Investments at Cost") now includes CASH and CRYPTO positions alongside STK/OPT. This is a presentation concern, not a tax concern.
- All cash still routed to 1101 regardless of currency (pre-existing issue).
- HMRC monthly rate variance still applies to CASH and CRYPTO trades (~5%).
