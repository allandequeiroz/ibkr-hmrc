ultrathink: 

Validate the generated trial balance against IBKR source reports.

These files belong to CAESARIS DENARII LIMITED, a UK micro-entity (FRS 105) with GBP base currency, trading through Interactive Brokers account U17419949.

**Files to review:**

- `analysis/16235546_trial_balance.html` -- generated trial balance (period ending 28 February 2026)
- `analysis/activity.csv` -- IBKR Activity Statement (Feb 21 2025 - Jan 28 2026)
- `analysis/realized.csv` -- IBKR Realized Summary (same period)
- `scripts/ibkr_trial_balance.py` -- the tool that generated the HTML from `analysis/business.csv`

**Methodology the tool uses:**

- Converts all foreign currency amounts to GBP using HMRC monthly spot rates fetched from `https://www.trade-tariff.service.gov.uk/uk/api/exchange_rates/files/monthly_csv_{year}-{month}.csv`
- Tracks cost basis per security using FIFO
- Only processes STK and OPT asset classes as investments (account 1200)
- Skips CASH (FX conversions) and CRYPTO (Paxos-custodied) trades entirely
- Sorts same-day trades with buys before sells for FIFO correctness
- Produces a pre-closing trial balance (income/expense accounts shown separately, no P&L summary account)

**Known variances:**

- HMRC monthly rates vs IBKR daily rates produce ~5% divergence on net realized P/L
- FX conversion gains/losses (~29K GBP per IBKR) are not captured
- Crypto P/L (~1K GBP) is excluded
- Investments account has a -1,334 GBP rounding residual from cumulative FIFO partial lot quantization

**Verify the following:**

1. Does net realized P/L (account 4200 credit minus account 5400 debit) approximately match the IBKR Realized Total for Stocks + Equity and Index Options from `analysis/realized.csv`? Sum column index 9 ("Realized Total") grouped by Asset Category, excluding rows where Symbol is "Total" or "Total (All Assets)".

2. Do these trial balance figures approximately match the corresponding IBKR Activity Statement values from the "Change in NAV" section of `analysis/activity.csv`?
   - Dividend Income (account 4000) vs "Dividends"
   - Foreign Withholding Tax (account 5000) vs "Withholding Tax"
   - Broker Commissions (account 5100) vs "Commissions" + "Commissions at Paxos"
   - Broker Fees (account 5200) vs "Other Fees"
   - Interest Paid (account 5600) vs "Interest"

3. Does the Listed Investments at Cost schedule (bottom of HTML) show only genuinely open positions? Cross-reference against `analysis/realized.csv` -- any symbol with Current Quantity = 0 should not appear.

4. Is the trial balance balanced (total debits = total credits)?

5. Fetch the HMRC monthly exchange rate CSV for April 2025 from `https://www.trade-tariff.service.gov.uk/uk/api/exchange_rates/files/monthly_csv_2025-4.csv` and verify the USD rate matches what the tool would use for April 2025 trades.

6. Flag any figures that look wrong, inconsistent, or warrant further investigation.

Present findings as a structured report with pass/fail per check and percentage variances where applicable.

**After reporting, fix any issues found:**

- If a check fails due to a bug in `scripts/ibkr_trial_balance.py`, fix the script.
- After fixing, re-run the tool to regenerate the HTML: `python scripts/ibkr_trial_balance.py analysis/business.csv --period-end 2026-02-28 --company "CAESARIS DENARII LIMITED" --output analysis/16235546_trial_balance.html`
- Re-validate the regenerated output against the same checks above.
- Repeat until all fixable checks pass.
- Document each fix in a new or updated file under `docs/discussions/`.
- If a variance is expected (e.g. HMRC rate divergence), note it as accepted rather than attempting a fix.

(no sandbox limits)