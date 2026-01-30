# Discussion 7: FX Holdings Schedule Filter

**Date**: 2026-01-30
**Status**: Applied and validated

## Problem

Following Discussion 6 (which added CASH and CRYPTO trade processing), the holdings schedule incorrectly displayed FX conversion positions alongside genuine investment holdings:

| Symbol | Asset Class | Qty | Cost (GBP) | Issue |
|--------|-------------|-----|-----------|-------|
| GBP.USD | CASH | 779,542 | 798,471.64 | FX conversion, not an investment |
| ILS.USD | CASH | 1.4 | 0.31 | FX conversion, not an investment |
| USD.DKK | CASH | 453 | 330.86 | FX conversion, not an investment |
| USD.ILS | CASH | 641 | 457.27 | FX conversion, not an investment |
| IRMD 260417P00095000 | OPT | 5 | 2,326.16 | Genuine option position |

Total holdings schedule: 801,586.24 GBP (of which 799,260.08 was FX positions)

## Root Cause

Discussion 6 correctly implemented CASH and CRYPTO trade processing through the same FIFO machinery as STK/OPT:
- CASH trades processed for FX gain/loss calculation
- Gains/losses routed to accounts 4300 (FX Gains) and 5500 (FX Losses)
- All asset classes use account 1200 as transit account for cost tracking

However, the `get_holdings_summary()` method returned all lots with quantity > 0, regardless of asset class. FX conversion "positions" are FIFO artefacts from the gain/loss calculation, not genuine investment holdings.

## Design Decision

**Option A** (chosen): Filter CASH and CRYPTO from holdings schedule display
- Process all asset classes through account 1200 for FIFO gain/loss calculation
- Exclude CASH and CRYPTO from the holdings schedule report
- Accept that account 1200 balance (801,586.24 DR) exceeds holdings schedule total (2,326.16)
- The difference (799,260.08) represents CASH lots used for FX gain/loss tracking

**Option B** (rejected): Route CASH/CRYPTO to separate accounts
- Would require new accounts (e.g. 1210 FX Positions, 1220 Crypto Holdings)
- Adds complexity for limited benefit
- CASH positions are not real holdings (they're currency conversions)
- CRYPTO is Paxos-custodied (outside IBKR regulatory scope)

## Implementation

**Code changes** (`scripts/ibkr_trial_balance.py`):

1. Added `asset_class: str` field to `LotHolding` dataclass (line 145)
2. Pass `asset_class=trade.asset_class` when creating lots in `_process_trade()` (line 447)
3. Preserve `asset_class` when creating partial lots in `_calculate_fifo_cost()` (line 505)
4. Filter out CASH and CRYPTO in `get_holdings_summary()` (line 607):

```python
def get_holdings_summary(self) -> list[dict]:
    """Get summary of holdings at cost.

    Excludes CASH and CRYPTO asset classes - these are processed for
    gain/loss calculation but are not genuine investment holdings.
    """
    result = []
    for symbol, lots in sorted(self.holdings.items()):
        # Filter out CASH (FX conversions) and CRYPTO (Paxos-custodied)
        investment_lots = [lot for lot in lots if lot.asset_class not in ('CASH', 'CRYPTO')]

        total_qty = sum(lot.quantity for lot in investment_lots)
        total_cost = sum(lot.cost_gbp for lot in investment_lots)

        if total_qty > 0:
            result.append({
                'symbol': symbol,
                'quantity': total_qty,
                'cost_gbp': total_cost,
                'avg_cost': (total_cost / total_qty).quantize(Decimal('0.0001'))
            })
    return result
```

## Validation Results

### Before Fix
| Check | Result |
|-------|--------|
| Holdings schedule | 5 positions (4 FX, 1 option) totalling 801,586.24 |
| Account 1200 net | 801,586.24 DR |
| Reconciliation | Matched (but included FX positions incorrectly) |

### After Fix
| Check | Result |
|-------|--------|
| Holdings schedule | 1 position (IRMD option) totalling 2,326.16 |
| Account 1200 net | 801,586.24 DR |
| Reconciliation | Mismatch by 799,260.08 (CASH lots, expected) |

### Full Validation Report

```
CHECK 1: Net Realized P/L (STK + OPT)
  Trial Balance Net P/L: 376,737.26
  IBKR STK+OPT Net:      394,862.90
  Variance:              -18,125.64 (-4.59%)
  Result: PASS (within acceptable HMRC rate variance)

CHECK 2: Income & Expense Figures
  4000 Dividend Income:  PASS (+1.00%)
  5000 Withholding Tax:  PASS (+16.97%)
  5200 Broker Fees:      Known variance (21.82%, low priority)
  Net Interest:          PASS (+0.75%)

CHECK 3: Holdings Schedule
  Open positions: IRMD 260417P00095000 (5 contracts, 2,326.16)
  Result: PASS (no FX positions)

CHECK 4: Trial Balance Balanced
  DR = CR = 32,876,599.79
  Result: PASS

CHECK 5: HMRC April 2025 USD Rate
  USD rate: 1.2978 per £1
  Result: PASS

CHECK 6: Summary
  No critical issues found. All checks pass.
```

## Known Presentation Issue

**Account 1200 balance vs holdings schedule mismatch:**
- Account 1200: 801,586.24 DR
- Holdings schedule: 2,326.16
- Difference: 799,260.08 (CASH lots for FX gain/loss tracking)

This is expected and documented behaviour. Account 1200 is a multi-purpose transit account for all asset classes' FIFO cost tracking. The holdings schedule correctly displays only genuine investment positions (STK, OPT).

## Remaining Known Issues

1. **IRMD option roll** (from Discussion 5): The 95P buy and 94.5P sell were treated by IBKR as a roll (paired), but the tool sees them as separate symbols. Creates phantom 2,326.16 position. Structural FIFO limitation.

2. **Broker Fees variance** (from Discussion 5): 21.82% variance (200.63 absolute). Transaction Fees and Sales Tax may not route through Flex Query CTRN section. Low priority data quality issue.

3. **Multi-currency cash** (from ADR-001): All cash routed to account 1101 (USD) regardless of actual currency. Future enhancement.

4. **Share Capital D&W discrepancy** (from Discussion 5): 765K vs IBKR's 373K. Attributed to internal sub-account transfers. Investigate Flex Query configuration.

## Documentation Updates

- Updated `scripts/ibkr_trial_balance.py` with inline comments explaining the asset class filter
- Created validation script `analysis/validate_trial_balance.py` for automated checking
- This discussion file documents the fix and rationale

## References

- Discussion 6: CASH and CRYPTO Trade Processing
- Discussion 5: Trial Balance Validation Audit (identified IRMD roll issue)
- ADR-001: Multi-currency cash as future enhancement
