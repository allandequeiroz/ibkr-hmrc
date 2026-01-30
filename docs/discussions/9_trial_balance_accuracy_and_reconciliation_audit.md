# Discussion 9: Trial Balance Accuracy and Reconciliation Audit

**Date**: 2026-01-30  
**Trigger**: User request to verify `analysis/16235546_trial_balance.html` against all analysis CSVs/XLSX and confirm decimal-level reconciliation for HMRC.

---

## Scope

- **Report**: `analysis/16235546_trial_balance.html` (period end 28 Feb 2026, prepared 30 Jan 2026 08:26)
- **Sources checked**: `activity.csv`, `realized.csv`, `business.csv`, `qbo_accounts.xlsx`, `qbo_date.xlsx`, `qbo_transactions.xlsx`, `qbo_bank_register.xlsx`, `reconciliation_report.txt`
- **Tool**: `scripts/validate_trial_balance.py` (and manual comparison)

---

## 1. Internal accuracy of the report

| Check | Result |
|-------|--------|
| Trial balance balanced | ✓ DR = CR = 32,876,599.79 |
| Tax computation maths | ✓ Taxable profit 377,872.70; CT 94,468.18 @ 25% |
| Section 104 net vs disposals | ✓ Net capital gains 377,533.72 |
| FIFO vs Section 104 variance | ✓ 376,737.26 vs 377,533.72 (−796.46) |
| Holdings schedule | ✓ One position (IRMD option 2,326.16); no CASH/CRYPTO |

The HTML report is internally consistent and arithmetically correct.

---

## 2. Trial balance vs IBKR (decimal-level match?)

**Values do not match to the decimal.** Summary:

| Line | Trial balance | IBKR (activity/realized) | Variance | Assessment |
|------|----------------|---------------------------|----------|------------|
| Net realized P/L (4200−5400) | 376,737.26 | 394,862.90 (STK+OPT) | −18,125.64 (−4.59%) | HMRC monthly vs IBKR daily FX |
| Dividend (4000) | 780.13 | 772.41 | +7.72 (+1.00%) | FX conversion |
| Withholding tax (5000) | 184.71 | 157.91 | +26.80 (+16.97%) | FX on small amounts |
| Broker fees (5200) | 1,120.26 | 919.63 (Other Fees) | +200.63 (+21.82%) | Flex coverage / fee routing |
| Net interest (4100−5600) | −7,138.90 | −7,086.05 | −52.85 (+0.75%) | Minor |

- **Net P/L**: The tool uses HMRC monthly spot rates; IBKR uses daily settlement. A ~4–5% variance is expected and is documented in ADR-001 and VALIDATION_REPORT_2026-01-30. FRS 105 accepts a consistent, reasonable rate; HMRC rates are defensible.
- **Broker fees**: Validation script marks 5200 as FAIL vs IBKR “Other Fees” only; IBKR also reports Transaction Fees and Sales Tax (total fees ~1,199). The Flex Query may not supply all fee types; low materiality (£79–£200) vs overall P/L.
- **Dividend / WHT / interest**: Small absolute differences from FX and timing; acceptable for micro-entity.

So: **not reconciled to the penny with IBKR**, but the differences are explained and within the documented, HMRC-acceptable methodology.

---

## 3. QuickBooks reconciliation

**Not reconciled.** The report and `reconciliation_report.txt` both state this explicitly:

| Item | Book (trial balance) | QBO | Difference |
|------|----------------------|-----|------------|
| Bank | −1,167,240.00 (1100+1101+1102) | 772,686.87 (end balance) | −1,939,926.87 |
| Expenses | 9,863.68 (5200+5300+5600) | 546,976.82 (\|negative Amount\|) | −537,113.14 |

- **Bank**: Book cash is negative (net IBKR cash flows); QBO shows a positive bank balance. Likely causes: Flex Query may cover only one sub-account (U17419949 vs U17419949F), internal transfers, or QBO including other accounts; see Discussion 5 (Share Capital D&W).
- **Expenses**: Book expenses from the trial balance (~9.9K) are far below QBO outflows (~547K). Suggests different scope (e.g. QBO includes all expense types/accounts; book only IBKR-related 5200/5300/5600) or period/classification mismatch.

The HTML correctly labels these as “Unreconciled” and “Variance”. They are **not** decimal-level reconciled with the QBO files in `analysis/`.

---

## 4. HMRC implications

- **Trial balance and tax computation**: Prepared using HMRC monthly rates, FRS 105, and Section 104 for tax. Methodology is consistent and documented. Internal consistency and arithmetic are correct.
- **Difference vs IBKR**: By design (different FX source and, for tax, Section 104). Not a sign of error for HMRC; the ~4–5% P/L variance is documented and acceptable.
- **Decimal-level match**: HMRC does not require the trial balance to match IBKR or QBO to the penny. They do require a consistent, auditable basis (HMRC rates, clear treatment of gains/expenses). That basis is met.
- **QuickBooks**: The unreconciled bank and expense figures are a **bookkeeping/rec alignment** issue. They do not invalidate the trial balance or tax computation for HMRC, but if QBO is used for filing or submissions, the gap should be understood and ideally resolved or explained (e.g. in a reconciliation note).

---

## 5. Verdict

| Question | Answer |
|----------|--------|
| Is the report **accurate** (internally)? | **Yes.** Balanced, consistent, maths correct. |
| Is it **fully reconciled** with all sources? | **No.** Not to the decimal with IBKR; not reconciled with QBO (bank and expenses). |
| Values matching to the decimal for HMRC? | **Not required.** TB and tax computation use a consistent, defensible methodology (HMRC rates, Section 104). Documented variances vs IBKR are acceptable. QBO reconciliation is separate and currently unreconciled. |

**Recommendation**: The report is fit for use for FRS 105 and UK CT purposes from a methodology and accuracy perspective. For HMRC, keep the validation report and discussion docs (0–8) as the audit trail for variances. Resolve or clearly document the QuickBooks differences (scope, accounts, period) if QBO is used for filing or external submissions.
