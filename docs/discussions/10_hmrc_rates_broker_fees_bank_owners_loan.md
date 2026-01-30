# Discussion 10: HMRC vs IBKR Rates, Broker Fees, Bank Scope, Owner's Loan

**Date**: 2026-01-30  
**Trigger**: User questions on (1) switching to IBKR daily rates, (2) fixing broker fees discrepancy, (3) single master account clarification, (4) adding owner's loan from `analysis/owners_loan.xlsx`.

---

## 1. Should we switch to IBKR daily rates?

**Recommendation: No. Keep HMRC monthly rates.**

| Criterion | HMRC monthly (current) | IBKR daily |
|-----------|------------------------|------------|
| **HMRC defensibility** | Official, published, auditable | Not independently verifiable |
| **FRS 105** | "Consistent and reasonable" – accepted | Same, but source is broker not HMRC |
| **Audit** | Auditor can verify from gov.uk | Would require IBKR data export |
| **Match to IBKR P/L** | ~4–5% variance | Would match IBKR closely |
| **ADR-001** | Explicit choice and rationale | Would reverse that decision |

The ~4.6% net P/L variance is a consequence of using HMRC rates. Switching to IBKR daily would improve match to IBKR but weaken the audit trail and ADR-001 rationale. For UK statutory and tax purposes, HMRC monthly rates remain the better choice.

**If you ever need IBKR-aligned figures** (e.g. internal dashboards), that could be a separate optional mode or report, not the default for the trial balance.

---

## 2. Broker fees: Transaction Fees and Sales Tax not in Flex

**Finding**: The Flex Query CTRN section in `business.csv` only contains these **Type** values:

- Other Fees  
- Broker Interest Paid / Broker Interest Received  
- Withholding Tax  
- Deposits/Withdrawals  
- Dividends  

There are **no** rows with Type = "Transaction Fees" or "Sales Tax". IBKR Activity Statement reports those separately (£100.23 Transaction Fees, £179.51 Sales Tax); they are either not included in the Flex Query export or appear under a different section (e.g. trade-level).

**Conclusion**: We cannot fix the 5200 vs IBKR "Other Fees" gap by parsing more from the Flex CSV – the data is not there. Options:

1. **Leave as is** (documented variance, low materiality).  
2. **Manual override**: Add an optional `--broker-fees-adjustment` (or similar) so you can add a one-off amount to 5200 if you have the figure from the Activity Statement.  
3. **Check Flex Query setup**: In IBKR Flex Query configuration, check whether "Transaction Fees" and "Sales Tax" can be included in Cash Transactions; if they can, add them and re-export.

Implementation choice: (1) for now; (2) easy to add if you want it.

---

## 3. Bank / single master account

You confirmed there is no sub-account – only the master, and you were the only operator. So the negative book cash (−1,167,240) is the **net IBKR cash position** (1100+1101+1102) from the Flex Query for the master account. QBO bank balance (772,686.87) is your **Barclays** (or other) bank. We are therefore comparing:

- **Book cash** = IBKR only (one broker account).  
- **QBO bank** = High street bank (e.g. Barclays).

They are different cash pools. To reconcile meaningfully we need either:

- **A**: Book cash to include **all** company cash (IBKR + Barclays), and QBO to include the same banks; or  
- **B**: Separate reconciliation: IBKR book vs IBKR bank, Barclays book vs Barclays in QBO.

Adding owner's loan from `owners_loan.xlsx` (Barclays and any other bank in that file) brings Barclays into the trial balance (new cash account 1103), so **book cash** becomes IBKR + Barclays and can be compared to QBO if QBO includes both.

---

## 4. Owner's loan – added to calculations

**Requirement**: Include director's/owner's loan and repayments so that (a) the trial balance reflects them, and (b) the large QBO "expenses" (e.g. ~547k) are explained in part by loan repayments.

**Source**: `analysis/owners_loan.xlsx` – sheet "owners loan", columns Date, Account, Amount.

**Accounts added**:

- **1103** – Cash at Bank – Other (Barclays / other non-IBKR bank).  
- **2101** – Director's / Owner's Loan (liability when company owes director).

**Logic** (for rows where Account is a company bank, i.e. not U6361921):

- **Amount > 0** (company receives): DR 1103, CR 2101 (director lent to company).  
- **Amount < 0** (company pays): DR 2101, CR 1103 (company repaid director).

**U6361921** rows are internal transfers (IBKR to IBKR); the company side is already in the Flex Query as deposits. We do **not** post those again from owners_loan.

**Reconciliation**:

- Book cash = 1100 + 1101 + 1102 + **1103**.  
- Loan repayments reduce cash (1103) and liability (2101); they are not expenses (5200/5300/5600), so expense alignment is unchanged except that QBO "expenses" can be interpreted as including repayments – we document that and, if desired, can add a reconciliation line "QBO outflows excluding loan repayments" using data from owners_loan.

Implementation: new argument `--owners-loan` (path to `owners_loan.xlsx`), loader in code, post to 1103/2101 after Flex processing, include 1103 in book_cash for QBO reconciliation.

**2026-01-30 – Improved owners_loan.xlsx format**: The spreadsheet was restructured into two explicit sections: **Summary: Director -> Business** (money in; e.g. total -514,005.62) and **Summary: Business -> Director** (money out; e.g. total 513,275.13). The parser in `apply_owners_loan()` detects these section headers in the first column and posts by section (Director->Business → DR 1103 CR 2101; Business->Director → DR 2101 CR 1103), using `abs(Amount)` so sign in the sheet does not need to match a single convention. U6361921 rows in the "Director -> Business" section are still skipped to avoid double-counting with Flex. Fallback: if section headers are not found, sign convention (Amount &gt; 0 = company receives, &lt; 0 = company pays) is used.

**2026-01-30 – owners_loan.pdf support**: If the Excel file uses references/formulas that pandas reads as NaN or incorrectly, `--owners-loan` can point to **analysis/owners_loan.pdf** instead. The PDF parser (pdfplumber) extracts text and uses standalone totals (-514,005.62 and 513,275.13) to split Director->Business vs Business->Director blocks, so only loan movements are posted (no salary/counter-credit from page 1). Requires `pip install pdfplumber`.
