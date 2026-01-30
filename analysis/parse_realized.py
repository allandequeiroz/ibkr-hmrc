"""
Parse IBKR Flex Query realized.csv to extract:
1. Realized Total values grouped by Asset Category (Stocks, Equity and Index Options)
   - Excluding "Total" and "Total (All Assets)" summary rows
2. Net quantity per symbol from Trades (summing all trade quantities)
   - Identifying symbols with net quantity == 0 vs non-zero
3. Specifically check IRMD's net quantity
"""

import csv
import sys
from collections import defaultdict
from decimal import Decimal, InvalidOperation

FILE_PATH = r"c:\dev\ibkr-hmrc\analysis\realized.csv"


def parse_decimal(val):
    """Parse a string to Decimal, handling commas in numbers and empty strings."""
    if not val or val.strip() == "":
        return Decimal("0")
    # Remove commas used as thousands separators (e.g. "6,011")
    cleaned = val.strip().replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal("0")


def main():
    # =========================================================================
    # PART 1: Realized Total by Asset Category from "Realized & Unrealized
    #         Performance Summary" section
    # =========================================================================
    stocks_realized_total = Decimal("0")
    options_realized_total = Decimal("0")
    stocks_symbols = []
    options_symbols = []

    # Also collect per-symbol realized totals
    stocks_by_symbol = {}
    options_by_symbol = {}

    # =========================================================================
    # PART 2: Net quantity per symbol from Trades section
    # =========================================================================
    # key: (asset_category, symbol), value: net quantity
    net_quantity = defaultdict(Decimal)

    with open(FILE_PATH, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if len(row) < 3:
                continue

            section = row[0].strip()
            row_type = row[1].strip()

            # --- Realized & Unrealized Performance Summary ---
            if section == "Realized & Unrealized Performance Summary" and row_type == "Data":
                asset_category = row[2].strip()
                symbol = row[3].strip() if len(row) > 3 else ""

                # Skip summary rows
                if asset_category in ("Total", "Total (All Assets)"):
                    continue

                # Realized Total is at index 9 (0-based)
                if len(row) > 9:
                    realized_total = parse_decimal(row[9])
                else:
                    continue

                if asset_category == "Stocks":
                    stocks_realized_total += realized_total
                    stocks_symbols.append(symbol)
                    stocks_by_symbol[symbol] = realized_total

                elif asset_category == "Equity and Index Options":
                    options_realized_total += realized_total
                    options_symbols.append(symbol)
                    options_by_symbol[symbol] = realized_total

            # --- Trades section: accumulate quantities ---
            elif section == "Trades" and row_type == "Data":
                # row[2] = DataDiscriminator (Order, etc.)
                data_disc = row[2].strip() if len(row) > 2 else ""
                if data_disc != "Order":
                    continue  # skip SubTotal, Total rows

                asset_cat = row[3].strip() if len(row) > 3 else ""
                currency = row[4].strip() if len(row) > 4 else ""
                symbol = row[5].strip() if len(row) > 5 else ""
                # Quantity is at index 7
                if len(row) > 7:
                    qty = parse_decimal(row[7])
                else:
                    continue

                net_quantity[(asset_cat, symbol)] += qty

    # =========================================================================
    # OUTPUT
    # =========================================================================
    print("=" * 80)
    print("PART 1: REALIZED TOTAL BY ASSET CATEGORY")
    print("(from 'Realized & Unrealized Performance Summary' section,")
    print(" excluding Total and Total (All Assets) rows)")
    print("=" * 80)

    print(f"\n--- STOCKS (STK) ---")
    print(f"Number of symbols: {len(stocks_symbols)}")
    print(f"Realized Total (sum of individual symbols): {stocks_realized_total}")
    print(f"Realized Total (formatted): GBP {stocks_realized_total:,.2f}")

    print(f"\n--- EQUITY AND INDEX OPTIONS (OPT) ---")
    print(f"Number of symbols: {len(options_symbols)}")
    print(f"Realized Total (sum of individual symbols): {options_realized_total}")
    print(f"Realized Total (formatted): GBP {options_realized_total:,.2f}")

    combined = stocks_realized_total + options_realized_total
    print(f"\n--- COMBINED (STK + OPT) ---")
    print(f"Combined Realized Total: {combined}")
    print(f"Combined Realized Total (formatted): GBP {combined:,.2f}")

    # Cross-check: print the file's own Total lines for verification
    print("\n--- CROSS-CHECK WITH FILE TOTALS ---")
    print("(Line 164) Stocks Total from file: 405,280.347191792")
    print("(Line 217) Options Total from file: -10,417.442706615")
    print("(Line 224) All Assets Total from file: 425,230.568539758")

    # =========================================================================
    # PART 2: NET QUANTITY (CURRENT POSITION) PER SYMBOL
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 2: NET QUANTITY FROM TRADES (Current Position)")
    print("=" * 80)

    zero_qty_symbols = []
    nonzero_qty_symbols = []

    for (asset_cat, symbol), qty in sorted(net_quantity.items()):
        if qty == 0:
            zero_qty_symbols.append((asset_cat, symbol, qty))
        else:
            nonzero_qty_symbols.append((asset_cat, symbol, qty))

    print(f"\n--- SYMBOLS WITH NET QUANTITY = 0 (fully closed) ---")
    print(f"Count: {len(zero_qty_symbols)}")
    for asset_cat, symbol, qty in zero_qty_symbols:
        print(f"  [{asset_cat}] {symbol}: {qty}")

    print(f"\n--- SYMBOLS WITH NET QUANTITY != 0 (open position) ---")
    print(f"Count: {len(nonzero_qty_symbols)}")
    for asset_cat, symbol, qty in nonzero_qty_symbols:
        print(f"  [{asset_cat}] {symbol}: {qty}")

    # =========================================================================
    # PART 3: IRMD SPECIFICALLY
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 3: IRMD CHECK")
    print("=" * 80)

    irmd_found = False
    for (asset_cat, symbol), qty in sorted(net_quantity.items()):
        if "IRMD" in symbol:
            print(f"  [{asset_cat}] {symbol}: net quantity = {qty}")
            irmd_found = True

    if not irmd_found:
        print("  IRMD not found in Trades section.")

    # Also show IRMD from the Realized Summary
    for sym, val in options_by_symbol.items():
        if "IRMD" in sym:
            print(f"  [Realized Summary] {sym}: Realized Total = {val}")

    # =========================================================================
    # PART 4: TOP 10 STOCKS BY REALIZED P/L (absolute value)
    # =========================================================================
    print("\n" + "=" * 80)
    print("PART 4: TOP 10 STOCKS BY REALIZED TOTAL (absolute value)")
    print("=" * 80)
    sorted_stocks = sorted(stocks_by_symbol.items(), key=lambda x: abs(x[1]), reverse=True)
    for sym, val in sorted_stocks[:10]:
        print(f"  {sym}: GBP {val:,.2f}")

    print("\n--- TOP 10 OPTIONS BY REALIZED TOTAL (absolute value) ---")
    sorted_options = sorted(options_by_symbol.items(), key=lambda x: abs(x[1]), reverse=True)
    for sym, val in sorted_options[:10]:
        print(f"  {sym}: GBP {val:,.2f}")


if __name__ == "__main__":
    main()
