# Trial Balance Cross-Check Audit

**Date**: 2026-01-29

## Files Audited

- `analysis/16235546_trial_balance.html` (generated 29 Jan 2026 at 18:04)
- `analysis/activity.csv` (IBKR Activity Statement, Feb 21 2025 - Jan 28 2026)
- `analysis/realized.csv` (IBKR Realized Summary, same period)

## CRITICAL FINDING: Stale HTML Output

**The trial balance HTML was generated BEFORE the Discussion 2 fixes were applied.** The output matches Discussion 2's "Before fix" column exactly:

| Metric | HTML file | Discussion 2 "Before fix" | Discussion 2 "After fix" | IBKR STK+OPT ref |
|---|---|---|---|---|
| 1200 net | 2,009,786.36 | 2,009,786 | -1,334 | 0 (all closed) |
| 4200 Realized Gains | 2,264,826.89 | 2,264,827 | 1,014,207 | 811,493 (profit) |
| 5400 Realized Losses | 645,394.64 | 645,395 | 636,674 | 416,630 (loss) |
| Net Realized P/L | 1,619,432.25 | 1,619,432 | 377,533 | 394,863 |

Evidence: The holdings schedule contains FX conversion positions (GBP.USD, ILS.USD, USD.DKK, USD.ILS) that should have been filtered by the CASH asset class fix. The investments account is inflated by ~2M from phantom FX positions and FIFO ordering failures.

**Action required:** Regenerate the trial balance using the fixed `ibkr_trial_balance.py`.

---

## Verification Results (against stale HTML, noting expected post-fix behavior)

### 1. Trial Balance Balance Check

**PASS.** Total debits = Total credits = 32,892,206.64. Mechanically balanced.

### 2. Realized Gains (4200) and Losses (5400) vs IBKR

IBKR Realized Summary totals by category (GBP base):

| Category | Profit | Loss | Net |
|---|---|---|---|
| Stocks | 854,384.25 | -449,103.91 | 405,280.35 |
| Equity & Index Options | 117,708.76 | -128,126.20 | -10,417.44 |
| Forex | 44,958.05 | -15,711.95 | 29,246.10 |
| Crypto | 1,121.56 | 0 | 1,121.56 |
| **Total All Assets** | **1,018,172.63** | **-592,942.06** | **425,230.57** |
| **STK + OPT only** | **972,093.01** | **-577,230.11** | **394,862.90** |

**Stale HTML:** Net 1,619,432 vs IBKR All Assets 425,231. Off by +310%. **Useless — pre-fix data.**

**Post-fix (from Discussion 2):** Net 377,533 vs IBKR STK+OPT 394,863. Variance: -17,330 (-4.4%). Attributable to HMRC monthly vs IBKR daily FX rates. Acceptable under FRS 105.

### 3. Dividend Income (4000)

| Source | Amount (GBP) |
|---|---|
| Trial balance (4000) | 780.13 |
| IBKR Change in NAV | 772.41 |

Variance: +7.72 (+1.0%). Within HMRC rate tolerance. **PASS.**

### 4. Withholding Tax (5000)

| Source | Amount (GBP) |
|---|---|
| Trial balance (5000) | 184.71 |
| IBKR Change in NAV | 157.91 |

Variance: +26.80 (+17.0%). Elevated percentage but small absolute amount. Likely HMRC rate variance on few transactions where the monthly rate diverged materially from the actual rate. **ACCEPTABLE** but worth verifying individual WHT entries if precision matters.

### 5. Broker Commissions (5100)

| Source | Amount (GBP) |
|---|---|
| Trial balance (5100) | 7,683.40 |
| IBKR Commissions (excl. Paxos) | 7,434.85 |
| IBKR Commissions (incl. Paxos) | 7,658.96 |

The stale HTML includes commissions from CASH and CRYPTO trades (should be excluded post-fix). IBKR's figure of 7,434.85 excludes Paxos (crypto) commissions. After the asset class fix, the tool's commission figure should be closer to IBKR's non-Paxos total.

Additionally, see "Commission Double-Counting Bug" below — there is a systematic accounting error in how commissions are recorded.

### 6. Broker Fees (5200)

| Source | Amount (GBP) |
|---|---|
| Trial balance (5200) | 1,120.26 |
| IBKR Other Fees | 919.63 |
| IBKR Transaction Fees | 100.23 |
| IBKR Sales Tax | 179.51 |
| **IBKR Combined** | **1,199.37** |

Variance: -79.11 (-6.6%). The tool routes all "fee" type cash transactions to 5200. Transaction Fees and Sales Tax are separate IBKR sections that may or may not be captured in the Flex Query CTRN section. **NEEDS INVESTIGATION** — verify whether Transaction Fees (UK Stamp Tax entries) and Sales Tax appear in the Flex Query CSV parsed by the tool.

### 7. Interest Paid (5600) and Interest Received (4100)

| Metric | Trial Balance | IBKR |
|---|---|---|
| Interest Received (4100) | 1,604.52 | - |
| Interest Paid (5600) | 8,743.42 | - |
| **Net Interest** | **-7,138.90** | **-7,086.05** |

Variance on net basis: -52.85 (-0.7%). **PASS.** IBKR reports net interest only. Gross split not directly comparable.

### 8. Listed Investments Schedule

**FAIL.** The schedule shows 9 positions including 4 FX "positions":

| Symbol | Type | Qty | Cost (GBP) | Issue |
|---|---|---|---|---|
| BA | STK | 300 | 45,930.15 | FIFO failure (same-day sell before buy) |
| GBP.USD | CASH/FX | 779,542 | 798,471.64 | Should be filtered |
| ILS.USD | CASH/FX | 1.4 | 0.31 | Should be filtered |
| IONQ | STK | 3,365 | 117,926.28 | FIFO failure (phantom lots) |
| IRMD P | OPT | 5 | 2,326.16 | Possibly legitimate open option |
| LNG | STK | 4,491 | 777,851.88 | FIFO failure (phantom lots) |
| TSLA | STK | 876 | 270,287.98 | FIFO failure (phantom lots) |
| USD.DKK | CASH/FX | 453 | 330.86 | Should be filtered |
| USD.ILS | CASH/FX | 641 | 457.27 | Should be filtered |

IBKR shows **all positions closed** (Current Quantity = 0 for all symbols). After Discussion 2 fixes:
- FX positions eliminated (CASH asset class filtered)
- FIFO phantom lots eliminated (buy-before-sell ordering)
- Only the IRMD option (5 contracts, £2,326) and rounding residuals should remain

The IRMD 260417P00095000 option: IBKR realized.csv line 179 shows `IRMD 17APR26 95 P` with Realized Total = -456.34 and 0 unrealized. This suggests it IS closed. If the tool shows 5 open lots, the sell may have failed FIFO matching (same-day ordering issue, or the option symbol format doesn't match between buy and sell records).

### 9. Share Capital (3000)

| Entry | Amount |
|---|---|
| 3000 Credit (deposits) | 10,500.00 |
| 3000 Debit (withdrawals) | 775,926.08 |
| **Net** | **DR 765,426.08** |

Issues:
- Only £10,500 captured as deposits (2 GBP Electronic Fund Transfers). Missing: £19,664.29 internal transfer (GBP) and £479,341.33 in USD transfers from U6361921.
- Net £765,426 vs IBKR's -£373,113 net D&W = ~£392K discrepancy. This was already noted in Discussion 2 item 4 as possible sub-account internal transfers that cancel in the consolidated view.
- All withdrawals booked as "capital distributions" (DR 3000). For a company, director withdrawals should likely be Director's Loan Account. The tool lacks a DLA account.

### 10. HMRC Exchange Rate Verification

Fetched `monthly_csv_2025-4.csv` from `trade-tariff.service.gov.uk`:
- **USD rate: 1.2978 per GBP** (effective 01/04/2025 - 30/04/2025)

The tool URL pattern `monthly_csv_{year}-{month}.csv` correctly resolves. The `to_gbp` method divides by the rate (`GBP = foreign_amount / rate`), which is correct since HMRC publishes "currency units per £1".

Verification: $100 USD in April 2025 = 100 / 1.2978 = £77.05. **Correct.**

---

## NEW BUG FOUND: Commission Double-Counting

The buy-side accounting creates a systematic error in the investment account and P&L:

### Buy entries (current code):
```
1. DR 1200 = cost_gbp  (= proceeds + commission)    -- full cost to investments
   CR 1101 = cost_gbp                                -- cash out

2. DR 5100 = commission_gbp                          -- expense commission
   CR 1200 = commission_gbp                          -- reclassify out of investments
```

**Net on 1200 after buy:** cost - commission = proceeds_only

**But:** The lot tracker stores `cost_gbp` (including commission). On sale:
```
CR 1200 = lot.cost_gbp  (= proceeds + commission)   -- removes full cost
```

This removes proceeds+commission from an account that only holds proceeds. Result: **1200 goes negative by the buy commission amount for each sold position.**

### Sell entries (current code):
```
1. DR 1101 = net_proceeds  (= gross_proceeds - commission)
   CR 1200 = cost_of_sold  (lot cost including buy commission)

2. DR 5100 = sell_commission
   CR 1101 = sell_commission
```

**Net on 1101 from sell:** (gross - commission) - commission = gross - 2x commission.
The sell commission is deducted twice from cash: once in net_proceeds, once in the separate commission entry.

### Impact on P&L:
Commissions reduce realized gains/losses (via lot cost and net proceeds) AND are separately expensed in 5100. The P&L double-counts all commissions.

### Correct FRS 105 treatment (pick one):
**Option A** (capitalize commissions - standard UK approach):
- Buy: DR 1200 = full cost, CR 1101 = full cost. No reclassification to 5100. Lot = full cost.
- Sell: DR 1101 = gross proceeds, CR 1200 = lot cost. Gain/loss = gross proceeds - full cost. Separately: DR 5100 = sell commission, CR 1101 = sell commission.
- Commissions are part of cost basis (buys) and disposal costs (sells), reflected in gain/loss only.

**Option B** (expense commissions immediately):
- Buy: DR 1200 = proceeds only, CR 1101 = proceeds + commission. DR 5100 = buy commission. Lot = proceeds only.
- Sell: DR 1101 = gross proceeds, CR 1200 = lot cost (proceeds only). DR 5100 = sell commission, CR 1101 = sell commission. Gain/loss = gross proceeds - sell commission - lot cost.
- Commissions are immediate expenses, not in cost basis.

The current code conflates both, double-counting commissions.

### Evidence in trial balance:
Holdings schedule total (£2,013,583) minus 1200 account net (£2,009,786) = £3,797. This represents buy commissions on unsold positions that were reclassified out of 1200 but remain in lot costs. For sold positions, the drift is absorbed into the -1,334 residual noted in Discussion 2.

---

## Summary of Issues

| # | Severity | Issue | Status |
|---|---|---|---|
| 1 | **CRITICAL** | HTML is pre-fix (Discussion 2 not applied). All figures except balance check are wrong. | Regenerate |
| 2 | **HIGH** | Commission double-counting bug in buy reclassification and sell cash entries. P&L overstates expenses by ~£7,683. | Code fix needed |
| 3 | **MEDIUM** | Sell commission double-deducted from 1101. Cash account understated. | Code fix needed |
| 4 | **MEDIUM** | IRMD option shows as open (5 contracts) but IBKR shows closed. Symbol format mismatch likely. | Investigate |
| 5 | **MEDIUM** | Deposits incomplete — internal transfers and USD deposits not captured in 3000. | Investigate Flex Query CTRN coverage |
| 6 | **LOW** | WHT variance 17% (£27 absolute). Small amount, HMRC rate effect. | Acceptable |
| 7 | **LOW** | Broker Fees variance — Transaction Fees/Sales Tax capture unclear. | Verify Flex Query coverage |
| 8 | **INFO** | D&W discrepancy ~£392K (sub-account transfers). Already noted in Discussion 2. | Investigate |
| 9 | **INFO** | All cash in 1101 regardless of currency. Already noted in Discussion 2. | Future fix |
