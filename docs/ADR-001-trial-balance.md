# ADR-001: IBKR to UK Trial Balance Architecture

**Status:** Accepted  
**Date:** 2025-01-29  
**Decision Makers:** Allan De Queiroz  

## Context

Caesaris Denarii Limited (Company No. 16235546) is a UK investment holding company incorporated 6 February 2025 with a 28 February year-end. The company trades US-listed securities through Interactive Brokers and requires:

1. Statutory accounts compliant with FRS 105 (Micro-entities Regime)
2. Trial balance for accountant/auditor
3. Supporting schedules for listed investments
4. Audit trail for HMRC enquiries

The company's IBKR account operates in USD. All transactions must be converted to GBP for UK reporting.

## Decision Drivers

1. **Regulatory compliance** - FRS 105 mandates historical cost for investments (no mark-to-market option for micro-entities)
2. **HMRC-defensible FX rates** - Must use published, verifiable exchange rates
3. **Audit trail** - Every journal entry traceable to source transaction
4. **Automation** - Manual reconciliation is error-prone and doesn't scale
5. **Simplicity** - Single Python script, no database, minimal dependencies

## Decisions

### 1. Accounting Framework: FRS 105

**Decision:** Apply FRS 105 (The Financial Reporting Standard applicable to the Micro-entities Regime).

**Rationale:**
- Company qualifies as micro-entity (turnover <£632k, assets <£316k, <10 employees)
- FRS 105 requires historical cost - simpler than FRS 102 fair value option
- Reduces disclosure requirements
- No requirement for cash flow statement

**Consequences:**
- Investments carried at cost, not market value
- Unrealized gains/losses not recognized
- Simpler accounts but less informative for management purposes

### 2. FX Rates: HMRC Monthly Spot Rates

**Decision:** Use HMRC monthly exchange rates published at trade-tariff.service.gov.uk.

**Alternatives Considered:**

| Option | Pros | Cons |
|--------|------|------|
| HMRC monthly rates | Official, defensible, consistent | Less precise than daily rates |
| Bank of England daily | More precise | Harder to audit, slight HMRC acceptance risk |
| IBKR transaction rates | Exact rates used | Not independently verifiable, potential manipulation concerns |
| Average rates | Smooths volatility | Not FRS 105 compliant for transactions |

**Rationale:**
- HMRC publishes these rates explicitly for customs/tax purposes
- CSV download available programmatically
- Same rate applies to entire month - simplifies reconciliation
- Auditor can independently verify

**Consequences:**
- Slight FX variance vs actual settlement rates
- Acceptable under FRS 105 which permits "consistent and reasonable" rate methodology

### 3. Cost Method: FIFO (First In, First Out)

**Decision:** Track cost basis using FIFO matching.

**Alternatives Considered:**

| Option | Pros | Cons |
|--------|------|------|
| FIFO | Simple, matches IBKR default | Not UK CGT compliant (Section 104) |
| Section 104 pooling | UK CGT compliant | Complex, requires share identification |
| Specific identification | Maximum flexibility | Requires explicit lot selection |
| Average cost | Simple | Not deterministic |

**Rationale:**
- FIFO is acceptable for financial statements (accounts ≠ tax return)
- Section 104 pooling only required for Corporation Tax computation
- CGT adjustments handled separately in CT600
- IBKR reports FIFO by default - easier to reconcile

**Consequences:**
- Trial balance uses FIFO cost
- Separate CGT computation needed for tax return using Section 104 pooling
- Document this clearly to avoid confusion

### 4. Data Source: IBKR Activity Flex Query

**Decision:** Use Activity Flex Query CSV export as primary data source.

**Alternatives Considered:**

| Option | Pros | Cons |
|--------|------|------|
| Activity Flex Query | Customizable, CSV/XML, programmatic | 365-day limit per export |
| Standard Activity Statement | Pre-formatted | Rigid structure, PDF awkward to parse |
| IBKR API | Real-time, unlimited history | Requires persistent connection, API complexity |
| Trade Confirmations | Legal trade record | Missing cash transactions |

**Rationale:**
- Flex Query includes all transaction types (trades, dividends, fees, deposits)
- CSV format easily parsed
- Field-level customization ensures we get exactly what's needed
- No API credentials required - manual export acceptable for annual accounts

**Consequences:**
- User must configure Flex Query correctly (documented in setup guide)
- Multi-year periods require multiple exports (365-day limit)
- No real-time sync - point-in-time export

### 5. Output Format: HTML Report

**Decision:** Generate standalone HTML file with embedded CSS.

**Alternatives Considered:**

| Option | Pros | Cons |
|--------|------|------|
| HTML | Portable, printable, no dependencies | Static |
| PDF | Professional, fixed layout | Requires wkhtmltopdf or similar |
| Excel | Accountant-friendly, editable | Requires openpyxl, formatting complexity |
| JSON | Machine-readable | Not human-friendly |
| CSV | Simple | No formatting, multiple files needed |

**Rationale:**
- HTML renders in any browser
- Embedded CSS means single file, no external dependencies
- Print to PDF if needed
- Accountants can copy/paste into their systems

**Consequences:**
- Manual step to convert to PDF if required
- Not directly importable to accounting software (future enhancement)

### 6. Architecture: Single Script, No Database

**Decision:** Implement as single Python script with no persistent storage.

**Alternatives Considered:**

| Option | Pros | Cons |
|--------|------|------|
| Single script | Simple, portable, auditable | Re-processes from scratch each run |
| SQLite database | Incremental updates, queries | State management, migration complexity |
| Cloud service | Multi-user, always-on | Overkill, security concerns |

**Rationale:**
- Annual accounts = annual run. No need for incremental processing.
- Full reprocessing ensures reproducibility
- No database means no state corruption risk
- Entire codebase in one file - easy to audit, version, share

**Consequences:**
- Reprocesses entire history each run (acceptable for <10k transactions)
- No incremental updates
- Stateless = reproducible

### 7. Journal Entry Granularity

**Decision:** Record individual journal entries per transaction, not summarized.

**Rationale:**
- Audit trail requires transaction-level detail
- Summarization loses information
- Accountant can summarize downstream if needed

**Consequences:**
- More verbose internal data structure
- Enables future detailed journal export if needed

## Technical Specifications

### Dependencies

```
Python 3.10+
├── requests (HTTP client for HMRC rates)
├── csv (stdlib)
├── decimal (stdlib, for precise arithmetic)
├── dataclasses (stdlib)
└── datetime (stdlib)
```

### Data Flow

```
IBKR Flex Query CSV
        │
        ▼
┌───────────────────┐
│  FlexQueryParser  │ ─── Extracts trades, cash transactions, positions
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  HMRCRateCache    │ ─── Fetches/caches HMRC monthly rates
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  TrialBalance     │ ─── Processes transactions, tracks lots, generates TB
│  Generator        │
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  HTML Report      │ ─── Renders trial balance + schedules
│  Generator        │
└───────────────────┘
        │
        ▼
    HTML File
```

### Error Handling Strategy

| Error Type | Handling |
|------------|----------|
| Missing HMRC rate | Raise exception with clear message |
| Unparseable CSV row | Warn to stderr, skip row, continue |
| Unknown transaction type | Classify as Other Fee/Income |
| FX rate fetch failure | Raise exception (no fallback) |
| Unbalanced trial balance | Report in output, don't fail |

### 8. Tax Computation Enhancement (2026-01-30)

**Decision:** Add UK Corporation Tax computation alongside the trial balance: Section 104 share pooling (same-day and 30-day matching), taxable profit, Corporation Tax liability, CT600 box mapping, and tax shield summary.

**Rationale:** FRS 105 trial balance is for financial statements; CT600 requires Section 104 pooling and tax adjustments. Dual tracking (FIFO for accounts, Section 104 for tax) keeps both outputs in one report.

**Consequences:** New modules `section_104_pooling.py` and `tax_computation.py`; `--management-expenses` CSV for all allowable management/deductible expenses not in the Flex data; HTML report includes Tax Computation Schedule, Interest Relief (ICR), CT Liability, Section 104 Disposals, Tax Shield Summary, CT600 Mapping, and FIFO vs Section 104 variance.

### 9. Single-command report with QuickBooks reconciliation (2026-01-30)

**Decision:** One command (`ibkr_trial_balance.py` with optional `--qbo-accounts` and `--qbo-date`) produces a single HTML report containing trial balance, tax computation, and QuickBooks reconciliation (bank and expense alignment). QBO load and comparison logic lives in a shared module (`qbo_reconciliation.py`) used by the main script and by the standalone `reconcile_qbo.py` (text report).

**Rationale:** User need: one run, one file for the accountant. QBO data is additive (reconciliation section); book figures remain from IBKR. Shared module keeps behaviour consistent and changes in one place.

**Consequences:** Optional `--qbo-accounts` and `--qbo-date` on `ibkr_trial_balance.py`; `qbo_reconciliation.py` with loaders and `get_reconciliation_data()`; HTML report includes "QuickBooks Reconciliation" section when those args are provided; `reconcile_qbo.py` refactored to use the same module. Documented in README, QUICKBOOKS_EXPORT.md (§6 Option A/B), and NOTES.md.

## Future Considerations

1. **Multi-currency cash tracking** - Separate accounts for EUR, CHF, etc.
2. **Section 104 pooling** - Implemented for tax (CT600); FIFO retained for FRS 105 accounts.
3. **Xero/QuickBooks export** - Generate importable journal entries
4. **PDF generation** - Native PDF output without browser
5. **IBKR API integration** - Direct data fetch instead of manual export
6. **Opening balance import** - Handle transferred-in positions

## References

- FRS 105: https://www.frc.org.uk/standards-codes-policy/accounting-and-reporting/frs-105
- HMRC Exchange Rates: https://www.trade-tariff.service.gov.uk/exchange_rates/monthly
- IBKR Flex Queries: https://www.ibkrguides.com/orgportal/performanceandstatements/flex.htm
- Section 104 Holdings: https://www.gov.uk/hmrc-internal-manuals/capital-gains-manual/cg51560
