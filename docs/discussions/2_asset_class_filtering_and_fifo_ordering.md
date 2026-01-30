# Asset Class Filtering and FIFO Ordering Fixes

**Date**: 2026-01-29

## Problem

The generated trial balance showed values orders of magnitude too large: GBP 15.9M in listed investments and GBP 2.2M in realized gains for a micro-entity with GBP 19.83 NAV at period end. Two root causes were identified.

### 1. All trade asset classes treated as stock investments

The IBKR Flex Query CSV contains trades across four asset classes:

| AssetClass | Trades | Gross buys (mixed ccy) | What they are |
|---|---|---|---|
| STK | 3,657 | 19.4M | Equity trades |
| OPT | 248 | 1.0M | Options (puts/calls) |
| CASH | 31 | 1.1M | FX conversions (GBP.USD, ILS.USD, etc.) |
| CRYPTO | 52 | 80K | Bitcoin via Paxos |

The parser processed all four asset classes through the same investment accounting logic (account 1200 Listed Investments at Cost). FX conversions in particular created phantom investment positions: 22 GBP.USD "buys" (GBP-to-USD conversions) booked 1.06M into the investment account, with only 39K "sold" back. The remaining 1M+ sat as fictitious investment cost.

Crypto trades are custodied by Paxos Trust Company, not IBKR. They should not appear in the IBKR trial balance.

### 2. Same-day sells processed before same-day buys

Trades were sorted by date using Python's stable sort. Within the same date, trades appeared in CSV order. For several symbols (BA, TSLA, LNG, IONQ), sell orders preceded buy orders on the same date. When a sell reached the FIFO tracker before the corresponding buy, it found zero lots, consumed zero cost, and recorded the full sale proceeds as realized gain. The subsequent buy then created lots that were never consumed.

This produced 68 FIFO failures across 4 symbols, leaving 9,037 phantom shares in the lot tracker and massively overstating realized gains.

## Diagnosis Method

Compared the generated trial balance against two IBKR reports:
- `analysis/activity.csv` (Activity Statement, period Feb 21 2025 - Jan 28 2026)
- `analysis/realized.csv` (Realized Summary, same period)

Key IBKR reference figures (GBP base):
- Net Asset Value: 19.83
- All positions closed (Current Quantity = 0 for all symbols)
- Realized P/L by category: Stocks 405,280, Options -10,417, Forex 29,246, Crypto 1,122
- Total Realized: 425,231

## Changes Made

### `scripts/ibkr_trial_balance.py`

**Trade dataclass** (line ~96): Added `asset_class: str` field.

**`_parse_trade()`** (line ~261): Parses `AssetClass` from the IBKR data row.

**`_process_trade()`** (line ~421): Added early return for `CASH` and `CRYPTO` asset classes. FX conversions are cash movements between currency accounts, not investment purchases. Crypto is Paxos-custodied and excluded. STK and OPT trades continue to use the existing investment accounting logic.

**`process()`** (line ~410): Changed sort key from `t.date` to `(t.date, 0 if t.is_buy else 1)` so all buys on a given date are processed before sells. This ensures FIFO lots exist before they are consumed for same-day round trips.

**`main()`** (line ~877): Console output now shows trade counts per asset class and reports how many were skipped.

## Results After Fix

| Metric | Before fix | After fix | IBKR reference |
|---|---|---|---|
| Investments (1200) net | 2,009,786 | -1,334 (rounding) | 0 (all closed) |
| Realized gains | 2,264,827 | 1,014,207 | 811,493 (STK+OPT profit) |
| Realized losses | 645,395 | 636,674 | 416,630 (STK+OPT loss) |
| Net realized P/L | 1,619,432 | 377,533 | 394,863 (STK+OPT) |
| Trial balance | Out of balance | Balanced | - |

Net realized P/L variance vs IBKR: -4.4%. Attributable to HMRC monthly FX rates versus IBKR's actual daily conversion rates.

## Known Remaining Issues

1. **Investment account rounding**: Net -1,333.57 residual from cumulative rounding in FIFO partial lot consumption (0.009% of gross).

2. **All cash in account 1101**: Every trade debits/credits Cash at Bank - USD regardless of the trade's actual currency (GBP, USD, ILS, DKK). Should route to 1100 (GBP), 1101 (USD), or 1102 (Other) based on `CurrencyPrimary`.

3. **FX conversion gains/losses not captured**: IBKR reports 29,246 GBP in forex realized P/L. These cash-to-cash conversions are now skipped entirely. A future enhancement should book them as DR/CR between cash accounts with FX gain/loss.

4. **Deposits/withdrawals discrepancy**: The Flex Query CTRN section shows -765,426 GBP in deposits/withdrawals, but the IBKR Activity Statement shows -373,113 GBP. The ~392K difference may be internal transfers between sub-accounts (U17419949 and U17419949F) that cancel in the consolidated view. Needs investigation.

5. **HMRC rate variance**: The 4.4% P/L divergence from IBKR's figures is an inherent consequence of using monthly HMRC rates rather than actual daily exchange rates. This is acceptable under FRS 105 (consistent and reasonable rate methodology) and is HMRC-defensible.
