# Parser Section Code and Trial Balance Fixes

**Date**: 2026-01-29

## Problems

Three bugs prevented the tool from producing output from real IBKR Flex Query CSV exports.

### 1. Parser found 0 rows (trades, cash transactions, positions)

The IBKR Flex Query CSV format uses two columns before the data fields:

```
"HEADER","TRNT","ClientAccountID","CurrencyPrimary",...
"DATA","TRNT","U17419949","GBP",...
```

Column 0 is the line type (`HEADER` or `DATA`), column 1 is the section code (`TRNT`, `CTRN`, `POST`, `CORP`, `RATE`).

The parser used `row[0]` as the section identifier. This meant:

- Every header row was stored under the key `"HEADER"`, overwriting previous headers
- Data rows with `row[0] == "DATA"` never matched any stored header key

Additionally, `_parse_row()` did not recognise the actual section codes `CTRN` (cash transactions) or `POST` (open positions) in its routing logic. Even if section lookup had worked, cash transactions and positions would have been silently dropped.

### 2. UnicodeEncodeError on Windows

`Path.write_text()` defaults to the system encoding on Windows (cp1252). The HTML template contains Unicode characters (`U+2713` check mark, `U+26A0` warning sign) that are not representable in cp1252.

### 3. Trial balance out of balance

`_calculate_retained_earnings()` created a single-sided credit entry to account 3200 (Profit/Loss for Period) without any offsetting debit. Since every transaction already generates balanced double-entry journal entries, this extra credit broke the balance by exactly the P&L amount.

This bug was masked while the parser returned 0 rows (zero debits = zero credits = balanced).

## Changes Made

### `scripts/ibkr_trial_balance.py`

**`_parse()`** (line ~186): Replaced heuristic header detection with explicit line type checking. Now uses `row[0]` for line type (`HEADER`/`DATA`) and `row[1]` for section code (`TRNT`, `CTRN`, `POST`, etc.). Headers are stored per section code, not per line type.

**`_parse_row()`** (line ~234): Added `CTRN` to cash transaction routing and `POST` to position routing.

**`process()`** (line ~417): Removed the `_calculate_retained_earnings()` call. The tool now produces a correct pre-closing trial balance where income and expense accounts carry their natural balances. The P&L for period is derivable from the income minus expense lines. Closing entries are the accountant's responsibility.

**`main()`** (line ~889): Added `encoding='utf-8'` to `write_text()` call.

## Verification

After fixes, running against `business.csv`:

- 3,988 trades parsed (was 0)
- 131 cash transactions parsed (was 0)
- 0 positions (correct, no POST data rows in export)
- Trial balance: balanced
- HTML report: written without encoding errors
