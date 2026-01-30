# IBKR Flex Query Setup for UK Trial Balance

## Overview

This guide configures an IBKR Activity Flex Query that exports all data needed to generate a FRS 105 compliant trial balance for a UK limited company.

## Step 1: Access Flex Queries

1. Log in to IBKR Client Portal
2. Navigate to **Performance & Reports** → **Flex Queries**
3. Under "Activity Flex Query", click the **+** button

## Step 2: Create New Activity Flex Query

**Query Name:** `UK_Trial_Balance`

### Sections to Include

Configure each section by clicking on it and selecting fields:

#### 1. Trades (REQUIRED)
Click "Trades" → Options: **Execution** → Select fields:

- [x] ClientAccountID
- [x] CurrencyPrimary
- [x] AssetClass
- [x] Symbol
- [x] Description
- [x] TradeDate
- [x] Quantity
- [x] Proceeds
- [x] IBCommission
- [x] NetCash
- [x] CostBasis
- [x] FifoPnlRealized
- [x] OrigTradePrice
- [x] Buy/Sell

Click **Save**

#### 2. Cash Transactions (REQUIRED)
Click "Cash Transactions" → Select groups:
- [x] Dividends
- [x] Withholding Tax
- [x] Payment In Lieu Of Dividends
- [x] Broker Interest Paid
- [x] Broker Interest Received
- [x] Other Fees
- [x] Deposits/Withdrawals

Then **Select All** fields and click **Save**

#### 3. Open Positions (REQUIRED)
Click "Open Positions" → Options: **Summary** → Select fields:

- [x] ClientAccountID
- [x] CurrencyPrimary
- [x] AssetClass
- [x] Symbol
- [x] Description
- [x] Quantity
- [x] MarkPrice
- [x] PositionValue
- [x] CostBasisPrice
- [x] CostBasisMoney

Click **Save**

#### 4. Corporate Actions (RECOMMENDED)
Click "Corporate Actions" → Options: **Detail** → **Select All** → **Save**

This captures stock splits, mergers, spin-offs that affect cost basis.

## Step 3: Delivery Configuration

| Setting                                    | Value                                |
| ------------------------------------------ | ------------------------------------ |
| Accounts                                   | U6361921                             |
| Format                                     | CSV                                  |
| Include header and trailer records?        | No                                   |
| Include column headers?                    | Yes                                  |
| Display single column header row?          | No                                   |
| Include section code and line descriptor?  | Yes                                  |
| Period                                     | Last Business Day (adjust as needed) |

## Step 4: General Configuration

Configure these EXACTLY as shown:

| Setting                                       | Value            |
| --------------------------------------------- | ---------------- |
| Profit and Loss                               | Default          |
| Include Cancelled Trades?                     | No               |
| Include Currency Rates?                       | Yes              |
| Include Audit Trail Fields?                   | No               |
| Display Account Alias in Place of Account ID? | No               |
| Breakout by Day?                              | No               |
| Date Format                                   | `yyyy-MM-dd`     |
| Time Format                                   | `HH:mm:ss`       |
| Date/Time Separator                           | `;` (semi-colon) |

## Step 5: Save and Run

1. Click **Continue**
2. Review settings, click **Create**
3. To run: Click the **▶** arrow next to your query
4. Select period (max 365 days per export)
5. Select **CSV** format
6. Click **Run**

## Running the Tool

```bash
# Install dependencies
pip install pandas requests --break-system-packages

# Run the trial balance generator
python ibkr_trial_balance.py UK_Trial_Balance_20250228.csv \
    --period-end 2026-02-28 \
    --company "CAESARIS DENARII LIMITED" \
    --output trial_balance.html
```

## What Gets Generated

### Trial Balance Accounts

| Code | Account | Type |
|------|---------|------|
| 1100 | Cash at Bank - GBP | Asset |
| 1101 | Cash at Bank - USD | Asset |
| 1102 | Cash at Bank - Other | Asset |
| 1200 | Listed Investments at Cost | Asset |
| 2100 | Accruals | Liability |
| 3000 | Share Capital | Capital |
| 3100 | Retained Earnings B/F | Capital |
| 3200 | Profit/(Loss) for Period | Capital |
| 4000 | Dividend Income (Gross) | Income |
| 4100 | Bank Interest Received | Income |
| 4200 | Realized Gains on Investments | Income |
| 4300 | Foreign Exchange Gains | Income |
| 5000 | Foreign Withholding Tax | Expense |
| 5100 | Broker Commissions | Expense |
| 5200 | Broker Fees | Expense |
| 5300 | Bank Charges | Expense |
| 5400 | Realized Losses on Investments | Expense |
| 5500 | Foreign Exchange Losses | Expense |
| 5600 | Interest Paid | Expense |

### FRS 105 Compliance Notes

1. **Historical Cost:** Investments carried at purchase cost, not fair value
2. **FX Translation:** All USD transactions converted to GBP using HMRC monthly spot rates
3. **Cost Method:** FIFO for determining cost of shares sold
4. **Recognition:** Gains/losses recognized only on disposal (not unrealized)
5. **Period End:** Cash balances retranslated at period-end rates (monetary items)

### Audit Trail

The tool maintains:
- Individual journal entries for each transaction
- FIFO lot tracking per security
- FX rates applied per transaction date

## Limitations & Manual Adjustments Needed

### Not Automatically Handled

1. **Opening balances** - If you transferred positions into IBKR, you need to manually input cost basis
2. **Section 104 pooling** - UK CGT uses share pooling, not FIFO. This tool uses FIFO for simplicity; adjust for tax returns
3. **Bed and breakfasting** - 30-day matching rules not implemented
4. **Director's loan account** - If you've extracted cash, this may be DLA not capital distribution
5. **Corporation Tax provision** - Accrue CT liability separately

### Multi-Year Periods

IBKR limits exports to 365 days. For your first accounting period (6 Feb 2025 to 28 Feb 2026), you'll need:
- Export 1: 6 Feb 2025 to 5 Feb 2026
- Export 2: 6 Feb 2026 to 28 Feb 2026

Run the tool on each export and manually consolidate, or modify the tool to accept multiple input files.

## Questions for Your Accountant

Before finalizing, clarify with your accountant:

1. **Director's remuneration** - Are you taking salary? How recorded?
2. **Qualifying shareholding** - Does the company hold >10% in any investment for substantial shareholding exemption?
3. **Trading vs Investment** - Classification affects loss relief; ensure CT600 filing as investment company is correct
4. **WHT reclaims** - US dividends face 15% WHT under treaty; are you claiming treaty relief?

---

*Generated for CAESARIS DENARII LIMITED (Company No. 16235546)*
*Accounting framework: FRS 105 (Micro-entities)*
*Year end: 28 February*
