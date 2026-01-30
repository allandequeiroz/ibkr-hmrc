ultrathink:
You are editing c:\dev\institutions (no sandbox limits)

# Full report in one command (trial balance + tax + management expenses + owner's loan + QuickBooks reconciliation)
python scripts/ibkr_trial_balance.py analysis/business.csv \
    --period-end 2026-02-28 \
    --company "CAESARIS DENARII LIMITED" \
    --output analysis/16235546_trial_balance.html \
    --management-expenses analysis/16235546_trial_balance.csv \
    --owners-loan analysis/owners_loan.pdf \
    --qbo-accounts analysis/qbo_accounts.xlsx \
    --qbo-date analysis/qbo_date.xlsx


---

Quick version
1. In QuickBooks Online
Go to Reports.
Run Transaction List by Account (or Bank Register if you have it).
Choose the bank account(s) and date range that match your trial balance.
Click Export / Print → Export to Excel.
Save the file into analysis/, e.g. analysis/qbo_bank_register.xlsx.

2. If you want CSV
Open the Excel file → File → Save As → choose CSV (Comma delimited).
Save again in analysis/, e.g. analysis/qbo_bank_register.csv.

3. For expenses
Reports → Transaction List by Date (or Profit and Loss) for the same period.
Export to Excel (then optionally Save As CSV) and put in analysis/, e.g. analysis/qbo_transactions.csv or analysis/qbo_pnl.csv.

4. Suggested filenames in analysis/
File	What it is
qbo_bank_register.xlsx or .csv	Bank transactions (for bank rec)
qbo_transactions.xlsx or .csv	All transactions by date (for expense alignment)
qbo_pnl.xlsx or .csv	P&L for the period (optional)

Use the same date range as your trial balance (e.g. 21 Feb 2025 – 28 Feb 2026). Full steps, QBO vs Desktop, and a short checklist are in docs/QUICKBOOKS_EXPORT.md.