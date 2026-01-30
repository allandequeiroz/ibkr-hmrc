# QuickBooks Export – Step by Step

Export bank and expense data from QuickBooks so you can drop the files into `analysis/` for reconciliation with the trial balance.

---

## 1. Accounting method: use Cash basis

The trial balance from this project uses **cash basis** for income and expenses (dividends, interest, fees are recorded when the cash appears in the IBKR data). Investments (buys/sells) use **trade date**.

When you run reports in QuickBooks for this reconciliation:

- Set the report or company preference to **Cash** (not Accrual), so income and expenses in the export match the trial balance.
- If QuickBooks asks “Cash vs Accrual” on the report, choose **Cash**.

That way the exported transactions align with what the tool produced.

---

## 2. Where to put the files

Save everything under the project’s **`analysis/`** folder. Use these filenames:

| File | Purpose |
|------|---------|
| **`analysis/qbo_bank_register.xlsx`** | Export from **Transaction Detail by Account** for the bank account(s). |
| **`analysis/qbo_transactions.xlsx`** | Export from **Transaction List by Date** for the same period. |
| **`analysis/qbo_accounts.xlsx`** | Use this file for **bank reconciliation** (same export as Transaction Detail by Account → save as `qbo_accounts.xlsx`). |
| **`analysis/qbo_date.xlsx`** | Use this file for **expense alignment** (same export as Transaction List by Date → save as `qbo_date.xlsx`). |

So in practice: export **Transaction Detail by Account** once and save as **`qbo_accounts.xlsx`** (or `qbo_bank_register.xlsx` if you prefer). Export **Transaction List by Date** once and save as **`qbo_date.xlsx`** (or `qbo_transactions.xlsx` if you prefer). Use `.csv` instead of `.xlsx` if your scripts expect CSV.

---

## 3. QuickBooks Online (QBO)

### A. Export reports to Excel (then CSV if you want)

1. Log in to **QuickBooks Online**.
2. Open **Reports** (left menu or search “Reports”).
3. Pick the report you need (see below).
4. Set the **date range** to match your trial balance period (e.g. 21 Feb 2025 – 28 Feb 2026).
5. Run the report.
6. Click **Export / Print** (or the export icon).
7. Choose **Export to Excel**.
8. Save the file into **`analysis/`** using the names below: **`qbo_accounts.xlsx`** for the bank report, **`qbo_date.xlsx`** for the transactions-by-date report.
9. If you need CSV: open the Excel file, then **File → Save As → CSV (Comma delimited)** and save again in `analysis/` (e.g. `qbo_accounts.csv`, `qbo_date.csv`).

If Excel opens in “Protected View”, click **Enable Editing** so you can save as CSV.

### B. Which reports to export

In Reports, search for “transaction” and use:

| What you need | Report to use | Save under `analysis/` as |
|---------------|----------------|---------------------------|
| **Bank reconciliation** | **Transaction Detail by Account** – pick the bank account(s) that receive IBKR funds / pay IBKR-related expenses. | **`qbo_accounts.xlsx`** (or `qbo_bank_register.xlsx`). |
| **Expense alignment** | **Transaction List by Date** – same date range; optionally filter by type (Expense, etc.). | **`qbo_date.xlsx`** (or `qbo_transactions.xlsx`). |

- **Transaction Detail by Account** for the bank account(s) → export to Excel → save as **`analysis/qbo_accounts.xlsx`** (for bank reconciliation). You can also keep a copy as `qbo_bank_register.xlsx` if you use that name.
- **Transaction List by Date** for the same period → export to Excel → save as **`analysis/qbo_date.xlsx`** (for expense alignment). You can also keep a copy as `qbo_transactions.xlsx` if you use that name.

**Order to run:**  
1. **Transaction Detail by Account** for the bank account(s) → export → save as **`analysis/qbo_accounts.xlsx`**.  
2. **Transaction List by Date** for the same period → export → save as **`analysis/qbo_date.xlsx`**.

- For **bank reconciliation**: use the file **`qbo_accounts.xlsx`** (export from Transaction Detail by Account for the account(s) that match trial balance cash 1100/1101/1102).
- For **expense alignment**: use the file **`qbo_date.xlsx`** (export from Transaction List by Date) to compare to trial balance expense accounts (5200, 5300, 5600, etc.).

### C. If you don’t see “Export to Excel”

- Try the **⋮** or **Export** option on the report screen.
- Some plans use **Print** and then “Save as PDF” or “Save as Excel” from the print dialog.
- If your plan doesn’t offer Excel, export **PDF** and keep it in `analysis/` (e.g. `qbo_accounts.pdf`, `qbo_date.pdf`) for reference; we can’t auto-reconcile from PDF, but you can still use it manually.

---

## 4. QuickBooks Desktop (QBD)

1. Open **Reports** (or **Reports** → **Banking** / **Accountant**).
2. Ensure reports use **Cash** basis (report settings or company preference).
3. Run **Transaction Detail by Account** (or **Transaction List by Account** / **Bank Register**) for the bank account(s), and/or **Transaction List by Date**.
4. Set the **From/To** dates to your trial balance period.
5. Use **Export** (or **Excel** / **Export to Excel**) and save into **`analysis/`**: **`qbo_accounts.xlsx`** for the bank report (Transaction Detail by Account), **`qbo_date.xlsx`** for the transactions report (Transaction List by Date).
6. If the export is Excel only and you need CSV, open the file and **File → Save As → CSV** in `analysis/` (e.g. `qbo_accounts.csv`, `qbo_date.csv`).

---

## 5. Checklist before reconciliation

- [ ] **Accounting method**: QuickBooks report (or company) set to **Cash** so it matches the trial balance.
- [ ] **Date range** matches the trial balance period (e.g. 21 Feb 2025 – 28 Feb 2026).
- [ ] **Bank**: **Transaction Detail by Account** run for the right bank account(s) → exported and saved as **`analysis/qbo_accounts.xlsx`** (or `qbo_bank_register.xlsx`).
- [ ] **Expenses**: **Transaction List by Date** run for the same period → exported and saved as **`analysis/qbo_date.xlsx`** (or `qbo_transactions.xlsx`).
- [ ] **Bank reconciliation** uses **`analysis/qbo_accounts.xlsx`**.
- [ ] **Expense alignment** uses **`analysis/qbo_date.xlsx`**.
- [ ] If scripts expect CSV: save as `.csv` in `analysis/` or export Excel then **File → Save As → CSV**.

Once these files are in `analysis/`, run the reconciliation script (see §6 below).

---

## 6. Running the reconciliation

From the repo root:

```bash
# Option A: Single HTML report (trial balance + tax + QuickBooks reconciliation in one file)
python scripts/ibkr_trial_balance.py analysis/business.csv --period-end 2026-02-28 \
  --company "YOUR COMPANY" --output analysis/trial_balance.html \
  --qbo-accounts analysis/qbo_accounts.xlsx --qbo-date analysis/qbo_date.xlsx

# Option B: Standalone reconciliation text report only
python scripts/reconcile_qbo.py --flex analysis/business.csv --period-end 2026-02-28
```

**Option A** gives one HTML file with trial balance, tax computation, and QuickBooks reconciliation. Use `--qbo-accounts` and `--qbo-date` with your QBO export paths.

**Option B** gives only the reconciliation as text (for `reconcile_qbo.py`: `--flex`, `--period-end`, `--qbo-accounts`, `--qbo-date`, `-o` for output path). The script runs the trial balance pipeline, loads QBO exports, and compares **bank** (book cash vs QBO balance; reconciled if difference &lt; 1p) and **expenses** (book vs QBO outflows; aligned if difference &lt; £1).

---

## 7. Understanding the bank reconciliation numbers

The report shows:

- **Book cash (1100+1101+1102+1103)** = net balance (debits − credits) of *all* cash accounts in the trial balance: IBKR (1100/1101/1102) and Barclays/other (1103). This can be **negative** when total cash outflows in the period (trades, withdrawals, fees, repayments) exceed inflows (deposits, sales). So a negative book cash does **not** mean “you have negative money”; it means “net movement across those four accounts is a net outflow.”
- **QBO bank (end Balance)** = the **closing balance** of *one* bank account in QuickBooks (e.g. Barclays), usually a positive number (what’s in that bank at period end).
- **Difference (bank)** = Book cash − QBO bank. So if book cash is −1,166,509.51 and QBO is 772,686.87, the difference is −1,939,196.38.

**Why it “smells”:** We are **not** comparing the same thing.

- **Book** = net of *all* company cash in the TB (IBKR + 1103). IBKR alone can have a large negative net (huge turnover, more out than in). 1103 is only the owners’ loan movements (e.g. 15k in, 513k out → net −498k). So the combined net can easily be negative.
- **QBO** = one bank’s closing balance (e.g. Barclays 772k).

So: **different scope** (all TB cash vs one bank) and **different meaning** (net TB position vs bank balance). The difference is expected. For a proper like‑for‑like check, reconcile **IBKR book vs IBKR** and **Barclays book (1103 or full ledger) vs Barclays in QBO** separately. The report’s “QuickBooks Reconciliation” section is a high‑level comparison; the note under the table in the HTML explains this.

