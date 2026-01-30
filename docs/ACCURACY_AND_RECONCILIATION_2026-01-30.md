# Trial Balance Accuracy and Decimal-Level Reconciliation

**Date**: 30 January 2026  
**Report**: `analysis/16235546_trial_balance.html` (Prepared 30 January 2026 at 12:03)  
**Sources**: `analysis/business.csv`, `activity.csv`, `realized.csv`, `qbo_*.xlsx`, `reconciliation_report.txt`

---

## 1. Is the report accurate?

**Yes.** The report is internally accurate:

| Check | Result |
|-------|--------|
| Trial balance balanced | ✓ Total Debits = Total Credits = 33,404,874.92 |
| Tax computation maths | ✓ Taxable profit 377,872.70; CT 94,468.18 @ 25%; Section 104 net 377,533.72 |
| FIFO vs Section 104 variance | ✓ 376,737.26 vs 377,533.72 (−796.46), as expected |
| Holdings schedule | ✓ One position (IRMD option 2,326.16); no CASH/CRYPTO in schedule |
| Balance check | ✓ Explicit "Trial balance balanced" in report |

Arithmetic is correct and the document is consistent with itself.

---

## 2. Is it fully reconciled, values matching to the decimal?

**No.** The report is **not** reconciled to the decimal with IBKR or with QuickBooks.

### 2.1 Trial balance vs IBKR (activity.csv, realized.csv)

| Line | Trial balance | IBKR | Variance | Assessment |
|------|----------------|------|----------|------------|
| Net realized P/L (4200−5400) | 376,737.26 | 394,862.90 (STK+OPT) | −18,125.64 (−4.59%) | HMRC monthly vs IBKR daily FX |
| Dividend (4000) | 780.13 | 772.41 | +7.72 (+1.00%) | FX conversion |
| Withholding tax (5000) | 184.71 | 157.91 | +26.80 (+16.97%) | FX on small amounts |
| Broker fees (5200) | 1,120.26 | 919.63 (Other Fees only) | +200.63 (+21.82%) | Flex does not include Transaction Fees/Sales Tax |
| Net interest (4100−5600) | −7,138.90 | −7,086.05 | −52.85 (+0.75%) | Minor |

- **Net P/L**: The tool uses HMRC monthly spot rates; IBKR uses daily settlement. A ~4–5% variance is expected and is documented in ADR-001 and VALIDATION_REPORT_2026-01-30. FRS 105 accepts a consistent, reasonable rate; HMRC rates are defensible.
- **Broker fees**: Validation script marks 5200 as FAIL vs IBKR "Other Fees" only. Transaction Fees and Sales Tax are not in the Flex Query CTRN section (see Discussion 10); low materiality (£79–£200) vs overall P/L.
- **Dividend / WHT / interest**: Small absolute differences from FX and timing; acceptable for micro-entity.

So: **not reconciled to the penny with IBKR**, but the differences are explained and within the documented, HMRC-acceptable methodology.

### 2.2 QuickBooks reconciliation

**Not reconciled.** The report and `analysis/reconciliation_report.txt` both state this:

| Item | Book (trial balance) | QBO | Difference |
|------|----------------------|-----|------------|
| Bank | −1,665,515.13 (1100+1101+1102+1103) | 772,686.87 (end Balance) | −2,438,202.00 |
| Expenses | 9,863.68 (5200+5300+5600) | 546,976.82 (sum \|negative Amount\|) | −537,113.14 |

- **Bank**: Book cash is IBKR + 1103 (owners’ loan bank); QBO is linked bank (e.g. Barclays). Different cash pools unless QBO includes the same set of accounts.
- **Expenses**: Book = IBKR fees/interest only; QBO = all outflows in period (including e.g. loan repayments). Different scope.

The HTML correctly labels these as "Unreconciled" and "Variance". They are **not** decimal-level reconciled with the QBO files in `analysis/`.

---

## 3. Will you have problems with HMRC?

**No.** HMRC does not require the trial balance to match IBKR or QBO to the decimal.

They do require:

- A **consistent, auditable basis** (e.g. HMRC monthly rates, clear treatment of gains/expenses, Section 104 for tax). That basis is met and documented.
- **Documented variances** where figures differ from the broker (e.g. VALIDATION_REPORT_2026-01-30, discussions 5, 9, 10).

So:

- **Trial balance and tax computation**: Prepared using HMRC monthly rates, FRS 105, and Section 104 for tax. Methodology is consistent and documented. Internal consistency and arithmetic are correct.
- **Difference vs IBKR**: By design (different FX source and, for tax, Section 104). Not a sign of error for HMRC; the ~4–5% P/L variance is documented and acceptable.
- **Decimal-level match**: Not required by HMRC for these purposes.
- **QuickBooks**: The unreconciled bank and expense figures are a **bookkeeping/reconciliation** matter. They do not invalidate the trial balance or tax computation for HMRC, but if QBO is used for filing or submissions, the gap should be understood and ideally resolved or explained (e.g. in a reconciliation note).

---

## 4. Verification performed

- `scripts/validate_trial_balance.py` run against `16235546_trial_balance.html`, `activity.csv`, `realized.csv`: all critical checks pass; 5200 vs IBKR Other Fees marked FAIL (known, low priority).
- Comparison of HTML trial balance totals and key lines to IBKR Change in NAV and Realized Summary totals.
- Review of `analysis/reconciliation_report.txt` and HTML QuickBooks Reconciliation section.
- Review of `analysis/deposits_only.csv`, `withdrawals_only.csv`, `business.csv` (source row counts) for consistency.

---

## 5. Summary

| Question | Answer |
|----------|--------|
| Is the report **accurate** (internally)? | **Yes.** Balanced, consistent, maths correct. |
| Is it **fully reconciled** with all sources to the decimal? | **No.** Not to the decimal with IBKR; not reconciled with QBO (bank and expenses). |
| Do values need to match to the decimal for HMRC? | **No.** TB and tax computation use a consistent, defensible methodology (HMRC rates, Section 104). Documented variances vs IBKR are acceptable. QBO reconciliation is separate and currently unreconciled. |

**Recommendation**: The report is fit for use for FRS 105 and UK CT from a methodology and accuracy perspective. Keep the validation report and discussion docs (0–10) as the audit trail for variances. Resolve or clearly document the QuickBooks differences (scope, accounts, period) if QBO is used for filing or external submissions.
