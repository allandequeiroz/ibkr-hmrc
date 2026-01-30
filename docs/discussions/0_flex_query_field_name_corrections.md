# Flex Query Field Name Corrections

**Date**: 2026-01-29

## Problem

The `IBKR_FLEX_QUERY_SETUP.md` documentation used human-readable field names (e.g. "Trade Price", "Mark To Market Value") that did not match the actual IBKR Flex Query field names in the configured `UK_Trial_Balance` query. This was verified against the actual query configuration exported as `docs/fields-available.pdf`.

The parser in `ibkr_trial_balance.py` also had lookup chains that did not include the actual field names, causing two fields to silently default to zero.

## Discrepancies Found

### Trades section (Options: Execution)

| Doc used          | Actual IBKR field  | Parser impact                  |
| ----------------- | ------------------ | ------------------------------ |
| Account ID        | ClientAccountID    | Not parsed (not needed)        |
| Asset Category    | AssetClass         | Not parsed (not needed)        |
| Trade Price       | OrigTradePrice     | **Bug**: defaulted to 0        |
| Currency          | CurrencyPrimary    | OK (parser checked both)       |
| Realized P/L      | FifoPnlRealized    | Not parsed (not needed)        |
| Commission        | IBCommission       | OK (parser checked both)       |

### Open Positions section (Options: Summary)

| Doc used              | Actual IBKR field | Parser impact                  |
| --------------------- | ----------------- | ------------------------------ |
| Account ID            | ClientAccountID   | Not parsed (not needed)        |
| Asset Category        | AssetClass        | Not parsed (not needed)        |
| Cost Basis            | CostBasisPrice    | Not parsed (CostBasisMoney is) |
| Mark To Market Price  | MarkPrice         | Not parsed (not needed)        |
| Mark To Market Value  | PositionValue     | **Bug**: defaulted to 0        |
| Currency              | CurrencyPrimary   | OK (parser checked both)       |

### Corporate Actions (Options: Detail)

No discrepancies. Doc said "Select All" and the actual query has all 47 fields selected.

### Cash Transactions

No discrepancies. Doc said "Select All" and the actual query has all 45 fields selected. All critical fields (`Date/Time`, `Amount`, `Type`, `Symbol`, `CurrencyPrimary`) are correctly handled by the parser.

### Delivery and General Configuration

Doc omitted several settings that are present in the actual query. Added to documentation for completeness.

## Parser Bug Impact

Both bugs were **non-functional** for trial balance output:

1. `Trade.price` (OrigTradePrice not matched): The `price` field is stored in the `Trade` dataclass but never used in accounting calculations. Cost is derived from `proceeds + commission`.

2. `Position.market_value` (PositionValue not matched): FRS 105 mandates historical cost. Market value is stored but never referenced in trial balance generation.

However, correct parsing is still necessary for audit trail completeness and potential future use.

## Changes Made

### Documentation

- `IBKR_FLEX_QUERY_SETUP.md`: Replaced all human-readable field names with actual IBKR system names. Added Options labels (Execution, Summary, Detail). Expanded Delivery and General Configuration to include all settings from the actual query.
- `README.md`: Updated minimum required fields to use actual IBKR field names.

### Code

- `scripts/ibkr_trial_balance.py:261`: Added `OrigTradePrice` to the trade price lookup chain.
- `scripts/ibkr_trial_balance.py:304`: Added `PositionValue` to the market value lookup chain.
