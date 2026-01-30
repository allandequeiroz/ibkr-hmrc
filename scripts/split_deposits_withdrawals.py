#!/usr/bin/env python3
"""
Split a Flex Query CSV into deposits-only and withdrawals-only (CTRN, Type=Deposits/Withdrawals).

Money in  = Amount > 0 (deposits, internal transfer in).
Money out = Amount < 0 (withdrawals, disbursements to Wise/Barclays etc.).

Usage:
  python scripts/split_deposits_withdrawals.py <flex.csv> [--out-dir DIR]

Creates:
  <out-dir>/deposits_only.csv    - CTRN rows with Amount > 0
  <out-dir>/withdrawals_only.csv - CTRN rows with Amount < 0
"""

import argparse
import csv
import sys
from pathlib import Path


def find_ctrn_header(rows: list[list[str]]) -> list[str] | None:
    for row in rows:
        if len(row) >= 2 and row[0].strip() == "HEADER" and row[1].strip() == "CTRN":
            return row
    return None


def main() -> None:
    ap = argparse.ArgumentParser(description="Split Flex CSV into deposits-only and withdrawals-only (CTRN D&W).")
    ap.add_argument("flex_csv", type=Path, help="Path to Flex Query CSV")
    ap.add_argument("--out-dir", type=Path, default=None, help="Output directory (default: same as CSV)")
    args = ap.parse_args()
    flex_path = args.flex_csv
    out_dir = args.out_dir if args.out_dir is not None else flex_path.parent
    if not flex_path.exists():
        print(f"Error: file not found: {flex_path}", file=sys.stderr)
        sys.exit(1)

    with open(flex_path, "r", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    header = find_ctrn_header(rows)
    if not header:
        print("Error: no CTRN HEADER row found in CSV", file=sys.stderr)
        sys.exit(1)
    try:
        idx_amount = header.index("Amount")
        idx_type = header.index("Type")
    except ValueError as e:
        print(f"Error: required column not found in CTRN header: {e}", file=sys.stderr)
        sys.exit(1)

    deposits: list[list[str]] = []
    withdrawals: list[list[str]] = []

    for row in rows:
        if len(row) <= max(idx_amount, idx_type):
            continue
        if row[0].strip() != "DATA" or row[1].strip() != "CTRN":
            continue
        if row[idx_type].strip() != "Deposits/Withdrawals":
            continue
        raw = row[idx_amount].strip().replace(",", "")
        if not raw:
            continue
        try:
            amt = float(raw)
        except ValueError:
            continue
        if amt > 0:
            deposits.append(row)
        elif amt < 0:
            withdrawals.append(row)

    out_dir.mkdir(parents=True, exist_ok=True)

    for name, data in [("deposits_only", deposits), ("withdrawals_only", withdrawals)]:
        out_path = out_dir / f"{name}.csv"
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(data)
        print(f"  {out_path}: {len(data)} rows")

    print(f"Deposits (money in):   {len(deposits)} rows")
    print(f"Withdrawals (money out): {len(withdrawals)} rows")


if __name__ == "__main__":
    main()
