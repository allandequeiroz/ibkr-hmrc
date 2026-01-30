# Discussion 4: Commission Capitalisation Fix

**Date:** 2026-01-29
**Status:** Applied and validated

## Problem

Discussion 3 identified a commission double-counting bug in `_process_trade()`. The buy side capitalised commissions into the FIFO lot cost (`cost_gbp = abs(proceeds) + commission`) but then reclassified the commission out of account 1200 into 5100:

```
BUY:
  DR 1200  cost_gbp (proceeds + commission)
  CR 1101  cost_gbp
  DR 5100  commission_gbp          ← reclassify
  CR 1200  commission_gbp          ← reclassify
```

Net effect: 1200 held only `proceeds` (commission reclassified out), but the FIFO lot stored `proceeds + commission`. On sale, `cost_of_sold` removed `proceeds + commission` from an account holding only `proceeds`, driving 1200 negative.

The sell side compounded the error by separately expensing sell commissions *and* deducting them from cash via net proceeds:

```
SELL:
  DR 1101  net_proceeds (= gross - commission)
  CR 1200  cost_of_sold (= lot with commission)
  DR 5100  sell_commission         ← double-deduction
  CR 1101  sell_commission         ← double-deduction from cash
```

Cash was reduced by sell commission twice: once in `net_proceeds`, once in the separate 5100/1101 entry.

### Impact

- Account 1200 accumulated a -£1,333.57 credit balance (negative asset)
- Account 5100 showed £7,431.79 in commissions that were *also* embedded in the gain/loss figures
- Total P&L double-counted all trade commissions

## Fix Applied

**Option A from Discussion 3: Capitalise commissions per FRS 105 Section 7.**

FRS 105 requires investments to be measured at cost, where cost includes purchase price plus transaction costs. On disposal, gain/loss is the difference between net disposal proceeds and carrying amount.

### Buy side

Removed the 5100/1200 commission reclassification. The full cost (proceeds + commission) stays in 1200 and in the FIFO lot:

```
BUY:
  DR 1200  cost_gbp (proceeds + commission)
  CR 1101  cost_gbp
```

### Sell side

Replaced the two-step conversion (gross proceeds and commission separately, then separate 5100 expense) with a single net-proceeds conversion:

```
SELL:
  net_proceeds_gbp = to_gbp(abs(proceeds) - commission)
  cost_of_sold = FIFO lot cost (includes buy commission)

  DR 1101  net_proceeds_gbp
  CR 1200  cost_of_sold
  DR/CR 4200/5400  gain_loss = net_proceeds_gbp - cost_of_sold
```

No 5100 entries. All commissions are implicit in investment cost and disposal proceeds.

## Verification

### Before fix

| Account | DR | CR | Net |
|---------|-----|-----|-----|
| 1200 | 15,053,925.87 | 15,055,259.44 | **-1,333.57** |
| 5100 | 7,431.79 | 0.00 | 7,431.79 |
| 4200 | 0.00 | 1,014,206.82 | — |
| 5400 | 636,673.81 | 0.00 | — |
| Net P/L | — | — | 377,533.01 |
| TOTAL | 31,926,023.31 | 31,926,023.31 | Balanced |

### After fix

| Account | DR | CR | Net |
|---------|-----|-----|-----|
| 1200 | 15,053,925.87 | 15,051,599.71 | **+2,326.16** |
| 5100 | — | — | **Eliminated** |
| 4200 | 0.00 | 1,014,206.86 | — |
| 5400 | 636,673.75 | 0.00 | — |
| Net P/L | — | — | 377,533.11 |
| TOTAL | 31,918,591.56 | 31,918,591.56 | Balanced |

### Key improvements

1. **1200 net = +2,326.16** — matches the holdings schedule total (open IRMD 95P position). Previously -1,333.57 (credit balance on an asset account).
2. **5100 eliminated** — no more double-counted commission expense. Commissions are fully absorbed in cost basis and disposal proceeds per FRS 105.
3. **Trial balance remains balanced** — both totals moved from 31,926,023.31 to 31,918,591.56 (decrease = removed 5100 gross entries minus rounding).
4. **Gain/loss figures changed by < £0.10** — rounding difference from converting net foreign proceeds as one amount vs converting gross and commission separately. Net P/L moved from 377,533.01 to 377,533.11.
5. **IBKR variance unchanged** — -4.39% vs IBKR £394,862.90. Entirely from HMRC monthly vs IBKR daily FX rates, accepted under FRS 105.

## Remaining issues (not addressed by this fix)

- Share Capital debit balance (£765K) — deposit/withdrawal routing issue
- Short IRMD 94.5P not tracked — structural limitation of FIFO-only tracker
- All cash routed to 1101 — known limitation per ADR
- FX gains/losses not captured — known limitation per ADR

## Commission audit trail

With 5100 eliminated, total commission spend is no longer visible in the trial balance. For audit purposes, the IBKR Activity Statement "Commissions" line (£7,434.85 + Paxos £224.11 = £7,658.96) serves as the primary record. Commissions are economically reflected in the gain/loss figures (reduced gains / increased losses).
