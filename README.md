# IBKR to UK Trial Balance

Converts Interactive Brokers Flex Query exports into FRS 105 compliant trial balances for UK limited companies.

## Purpose

Investment holding companies with IBKR accounts need proper books for Companies House filing and HMRC. This tool:

- Ingests IBKR Activity Flex Query CSV exports
- Converts USD transactions to GBP using official HMRC monthly rates
- Tracks cost basis per security (FIFO)
- Produces a balanced trial balance with supporting schedules

## Requirements

- Python 3.10+
- Internet access (fetches HMRC rates)

```bash
pip install pandas requests --break-system-packages
```

## Usage

```bash
python ibkr_trial_balance.py <flex_query.csv> \
    --period-end YYYY-MM-DD \
    --company "YOUR COMPANY NAME" \
    --output trial_balance.html
```

### Arguments

| Argument | Required | Description |
|----------|----------|-------------|
| `flex_query.csv` | Yes | IBKR Activity Flex Query export |
| `--period-end` | Yes | Accounting period end date |
| `--company` | No | Company name for report header |
| `--output` | No | Output file path (default: `trial_balance_YYYY-MM-DD.html`) |
| `--management-expenses` | Yes when you have such expenses | CSV of management/deductible expenses to include in the tax computation (description, amount_gbp, date). Include all allowable expenses not already in the Flex data so taxable profit is correct. |
| `--owners-loan` | No | Excel (owners_loan.xlsx) or **PDF** (owners_loan.pdf) with director's loan movements. Company bank rows post to 1103/2101; U6361921 excluded (in Flex). Use PDF if the spreadsheet uses references/formulas that don't read correctly. |
| `--qbo-accounts` | No | QBO Transaction Detail by Account (bank). When provided with `--qbo-date`, embeds QuickBooks reconciliation in the same HTML report. |
| `--qbo-date` | No | QBO Transaction List by Date (expenses). When provided with `--qbo-accounts`, embeds QuickBooks reconciliation in the same HTML report. |

## Output

One command produces a single HTML report. When `--qbo-accounts` and `--qbo-date` are provided, the report includes:

1. **Trial Balance** - All accounts with debits/credits, grouped by category
2. **Tax Computation** (if modules loaded) - Taxable profit, dividend exemption, management expenses, interest relief (ICR), Corporation Tax liability, Section 104 disposals, Tax Shield Summary, CT600 box mapping, FIFO vs Section 104 variance
3. **QuickBooks Reconciliation** (if `--qbo-accounts` and/or `--qbo-date` given) - Bank and expense alignment (book vs QBO)
4. **Holdings Schedule** - Listed investments at cost with FIFO lot detail
5. **Balance Check** - Confirms debits = credits

## Chart of Accounts

| Code | Account | Normal Balance |
|------|---------|----------------|
| 1100 | Cash at Bank - GBP | Debit |
| 1101 | Cash at Bank - USD | Debit |
| 1102 | Cash at Bank - Other CCY | Debit |
| 1103 | Cash at Bank - Other (e.g. Barclays; from owners_loan.xlsx or owners_loan.pdf) | Debit |
| 1200 | Listed Investments at Cost | Debit |
| 2100 | Accruals and Deferred Income | Credit |
| 2101 | Director's / Owner's Loan | Credit |
| 3000 | Share Capital | Credit |
| 3100 | Retained Earnings B/F | Credit |
| 3200 | Profit/(Loss) for Period | Credit |
| 4000 | Dividend Income (Gross) | Credit |
| 4100 | Bank Interest Received | Credit |
| 4200 | Realized Gains on Investments | Credit |
| 4300 | Foreign Exchange Gains | Credit |
| 5000 | Foreign Withholding Tax | Debit |
| 5100 | Broker Commissions | Debit (unused — commissions capitalised in cost) |
| 5200 | Broker Fees | Debit |
| 5300 | Bank Charges | Debit |
| 5400 | Realized Losses on Investments | Debit |
| 5500 | Foreign Exchange Losses | Debit |
| 5600 | Interest Paid | Debit |

## IBKR Flex Query Setup

See `IBKR_FLEX_QUERY_SETUP.md` for detailed configuration instructions.

Minimum required fields:

**Trades section** (Options: Execution):

- TradeDate, Symbol, Buy/Sell, Quantity, OrigTradePrice, CurrencyPrimary, Proceeds, IBCommission

**Cash Transactions section** (Options: Select All fields):

- Date/Time, Type, Symbol, Amount, CurrencyPrimary
- Groups: Dividends, Withholding Tax, Broker Interest, Other Fees, Deposits & Withdrawals

**General Configuration:**

- Date format: `yyyy-MM-dd`
- Output format: CSV with column headers
- Include section code and line descriptor: Yes

## Accounting Treatment

| Item | Treatment |
|------|-----------|
| Framework | FRS 105 (Micro-entities) |
| Investments | Historical cost (not fair value) |
| Gain/Loss Recognition | On disposal only |
| Transaction Costs | Capitalised in investment cost (buy) and deducted from disposal proceeds (sell) per FRS 105 s.7 |
| FX Rates | HMRC monthly spot rates |
| Cost Method | FIFO |
| Cash FX | Retranslated at period-end |

## Asset Class Handling

| AssetClass | Treatment |
|---|---|
| STK (Stocks) | Processed as Listed Investments at Cost (account 1200). Gains/losses to 4200/5400. Holdings schedule: included. |
| OPT (Options) | Processed as Listed Investments at Cost (account 1200). Gains/losses to 4200/5400. Holdings schedule: included. |
| CASH (FX) | Processed through FIFO for gain/loss calculation. Gains/losses to FX accounts (4300/5500). Holdings schedule: excluded (not genuine holdings). |
| CRYPTO | Processed through FIFO for gain/loss calculation. Gains/losses to 4200/5400. Holdings schedule: excluded (Paxos-custodied). |

**Note**: All asset classes use account 1200 as a transit account for FIFO cost tracking. The holdings schedule filters out CASH and CRYPTO, displaying only genuine investment holdings (STK, OPT). This creates an expected mismatch: account 1200 balance includes all asset classes, while the holdings schedule total includes only STK/OPT.

## Limitations

1. **Opening balances** - Not handled. If positions transferred in, manually adjust cost basis.
2. **Section 104 pooling** - Trial balance uses FIFO for accounts. Section 104 pooling and tax computation are integrated: the HTML report includes tax computation, CT liability, and CT600 mapping when `section_104_pooling` and `tax_computation` modules are available.
3. **Multi-currency cash** - All foreign cash mapped to 1101 (USD). Extend for EUR/other.
4. **Corporate actions** - Stock splits parsed but complex restructurings may need manual review.
5. **365-day export limit** - IBKR caps exports at 1 year. Run multiple exports for longer periods.
6. **FX conversion gains/losses** - Captured via FIFO. FX trades (CASH asset class) are processed for gain/loss calculation; gains/losses routed to accounts 4300/5500. CASH positions excluded from holdings schedule (not genuine holdings). HMRC monthly rate variance applies.
7. **Crypto trades** - Processed through same FIFO logic as STK/OPT. Paxos-custodied positions excluded from holdings schedule but gains/losses tracked for tax purposes (routed to 4200/5400).
8. **Account 1200 reconciliation** - Account 1200 balance includes all asset classes (STK, OPT, CASH, CRYPTO) for FIFO tracking. Holdings schedule total includes only STK/OPT. Expected mismatch documented in Discussion 7.
9. **HMRC rate variance** - Net realized P/L may diverge ~5% from IBKR's figures due to monthly HMRC rates vs daily actual rates. This is FRS 105 compliant.
10. **Option rolls** - The tool tracks FIFO per symbol. If IBKR pairs an option close against a different strike (roll), the tool sees mismatched symbols: the original lot stays open (phantom position) and the closing trade has zero cost (phantom gain). Manual adjustment required.

## File Structure

```
.
├── README.md                           # This file
├── IBKR_FLEX_QUERY_SETUP.md           # IBKR Flex Query configuration guide
├── CLAUDE.md                           # Project instructions for AI assistants
├── research-integrity-guidelines.md    # Research integrity standards
├── requirements.txt                    # Python dependencies
├── config/
│   └── project.conf                    # ClickHouse, FMP API, pipeline settings
├── scripts/
│   ├── ibkr_trial_balance.py          # Main trial balance tool
│   ├── section_104_pooling.py         # Section 104 pooling for UK tax (CT600)
│   ├── tax_computation.py             # Tax computation, CT liability, CT600 mapping
│   ├── ibkr_trial_balance-gemini.py   # Alternative parser (Standard Statements)
│   ├── parse_realized.py              # Realized P/L extraction utility
│   ├── validate_trial_balance.py      # Trial balance vs IBKR validation
│   ├── validate_tax_computation.py    # Tax computation validation
│   ├── qbo_reconciliation.py           # QBO loaders and reconciliation data (used by main script and reconcile_qbo)
│   └── reconcile_qbo.py                # Standalone reconcile TB vs QuickBooks (text report)
├── analysis/
│   ├── business.csv                    # IBKR Flex Query export (input)
│   ├── activity.csv                    # IBKR Activity Statement (validation)
│   ├── realized.csv                    # IBKR Realized Summary (validation)
│   └── 16235546_trial_balance.html    # Generated trial balance output
└── docs/
    ├── ADR-001-trial-balance.md       # Architecture decisions
    └── discussions/                    # Design decisions and audit history
```

## License

Internal use. Not for redistribution.
