# Isolating Deposits and Withdrawals (Money In / Money Out)

This guide explains how to get from IBKR a clear view of **money in** (deposits: direct transfer or internal transfer to the company’s IBKR account) and **money out** (withdrawals: from IBKR to Wise/Barclays and then to you as director loan repayments).

---

## 1. What you’re isolating

| Direction | Meaning | In IBKR Flex |
|-----------|--------|----------------|
| **Money in (deposits)** | You putting your own money into the company: direct transfer from personal bank to IBKR, or internal transfer into the company’s IBKR account. | Cash Transactions, Type = Deposits/Withdrawals, **Amount &gt; 0** |
| **Money out (withdrawals)** | Company paying you back: moving cash from IBKR to Wise/Barclays and then to yourself (director loan repayments). | Cash Transactions, Type = Deposits/Withdrawals, **Amount &lt; 0** |

The **Director Repayment Due** (e.g. 514,005.62 you put in) is the total you lent; the withdrawals are the repayments the company has made to you.

---

## 2. Flex Query: same query, then filter

IBKR Activity Flex does **not** let you define a query that returns *only* deposits. You get **Cash Transactions** with the **Deposits/Withdrawals** group, which includes both. So:

1. Use your existing **Activity Flex Query** (e.g. `UK_Trial_Balance`) that includes **Cash Transactions** and the **Deposits/Withdrawals** group (see `IBKR_FLEX_QUERY_SETUP.md`).
2. Run the query and download the CSV as usual.
3. Isolate **deposits** and **withdrawals** from that CSV as below.

**Optional: minimal “D&amp;W only” query**

If you only want deposits and withdrawals (no trades, no dividends, etc.):

1. Create a **new** Activity Flex Query, e.g. `UK_Deposits_Withdrawals`.
2. Include **only**:
   - **Cash Transactions** → enable **Deposits/Withdrawals** only (you can leave other groups off).
   - **Select All** fields in Cash Transactions.
3. Set the same **Delivery** and **Date** as your main query, then run and download the CSV.

You still get both deposits and withdrawals in one file; isolation is done after export.

---

## 3. Isolating deposits vs withdrawals in the export

In the Flex CSV, **Cash Transactions** rows have:

- **Line type:** first column = `"DATA"`, second = section code **`CTRN`**.
- **Type:** `Deposits/Withdrawals` for all D&amp;W.
- **Amount:**  
  - **Positive** = money **in** (deposit / internal transfer in).  
  - **Negative** = money **out** (withdrawal / disbursement).

So:

| To isolate | Rule in CTRN rows |
|------------|-------------------|
| **Deposits only (money in)** | `Type` = Deposits/Withdrawals and **Amount &gt; 0** |
| **Withdrawals only (money out)** | `Type` = Deposits/Withdrawals and **Amount &lt; 0** |

Typical **Description** values (for reference):

- **Money in:** e.g. `CASH RECEIPTS / ELECTRONIC FUND TRANSFERS`, or internal transfer descriptions (e.g. “Internal Transfer In …”).
- **Money out:** e.g. `DISBURSEMENT INITIATED BY …`.

---

## 4. Option A: Filter in Excel

1. Open the Flex CSV in Excel (or save as `.xlsx`).
2. Ensure the **CTRN** header row is visible (row with section code `CTRN` in column B).
3. Find the **Amount** and **Type** columns (in a typical export, Amount and Type are near the end of the CTRN header).
4. Add a filter to the sheet (Data → Filter).
5. **Deposits only:** Filter **Type** = `Deposits/Withdrawals` and **Amount** &gt; 0. Copy or save this view (e.g. “Deposits only” sheet).
6. **Withdrawals only:** Filter **Type** = `Deposits/Withdrawals` and **Amount** &lt; 0. Copy or save (e.g. “Withdrawals only” sheet).

You can then sum Amount by period, or match dates/amounts to your Director Repayment Due ledger (e.g. owners_loan.xlsx / Director Repayment Due report).

---

## 5. Option B: Split with a script

From the repo root, using your Flex CSV (e.g. `analysis/business.csv`):

```bash
python scripts/split_deposits_withdrawals.py analysis/business.csv --out-dir analysis
```

This will create:

- **`analysis/deposits_only.csv`** – CTRN rows with Type = Deposits/Withdrawals and Amount &gt; 0 (money in).
- **`analysis/withdrawals_only.csv`** – CTRN rows with Type = Deposits/Withdrawals and Amount &lt; 0 (money out).

Both files keep the same structure (including HEADER row) so you can re-use them or open in Excel. If `scripts/split_deposits_withdrawals.py` does not exist yet, use Option A (Excel) or the one-liner below.

---

## 6. Matching to your Director Repayment Due

- **Deposits (money in)** should align with the 514,005.62 you put in (direct + internal transfers into the company’s IBKR).
- **Withdrawals (money out)** should align with the transactions you see in the “Director Repayment Due” report (IBKR → Wise/Barclays → you).

Use the **Date** and **Amount** columns in:

- `deposits_only.csv` / filtered deposits, and  
- `withdrawals_only.csv` / filtered withdrawals  

to reconcile with:

- Your owners_loan.xlsx, and  
- The Director Repayment Due ledger (e.g. 20,000; 207,000; 219,997.84; 777.29; 1,000; 64,500; etc.).

---

## Summary

| Goal | How |
|------|-----|
| Get D&amp;W data from IBKR | Use existing Activity Flex Query with Cash Transactions → Deposits/Withdrawals (or a minimal query with only that group). |
| Isolate **deposits (money in)** | In the Flex CSV, keep only CTRN rows with Type = Deposits/Withdrawals and **Amount &gt; 0**. |
| Isolate **withdrawals (money out)** | Keep only CTRN rows with Type = Deposits/Withdrawals and **Amount &lt; 0**. |
| Do it in Excel | Open CSV, filter on Type and Amount as above. |
| Do it by script | Use `scripts/split_deposits_withdrawals.py` to produce `deposits_only.csv` and `withdrawals_only.csv`. |

There is no Flex Query that returns *only* deposits; use one export and then isolate in Excel or with the script.
