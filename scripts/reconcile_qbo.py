#!/usr/bin/env python3
"""
Reconcile trial balance (IBKR) with QuickBooks exports.

Uses:
- analysis/qbo_accounts.xlsx  (Transaction Detail by Account – bank) for bank reconciliation
- analysis/qbo_date.xlsx      (Transaction List by Date) for expense alignment
- Trial balance from running ibkr_trial_balance pipeline (business.csv)

Run from repo root:
  python scripts/reconcile_qbo.py [--flex analysis/business.csv] [--period-end 2026-02-28]

Output: reconciliation report (console + optional analysis/reconciliation_report.txt).

Alternatively, pass --qbo-accounts and --qbo-date to scripts/ibkr_trial_balance.py to embed
the same reconciliation in the single HTML report.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from qbo_reconciliation import get_reconciliation_data


def get_book_figures(
    flex_path: Path,
    period_end: str,
    owners_loan_path: Path | None = None,
) -> dict[str, Decimal] | None:
    """Run trial balance pipeline; return accounts dict (code -> balance: debit - credit)."""
    try:
        from ibkr_trial_balance import (
            FlexQueryParser,
            HMRCRateCache,
            TrialBalanceGenerator,
            apply_owners_loan,
        )
    except ImportError:
        return None
    period = datetime.strptime(period_end, "%Y-%m-%d").date()
    rate_cache = HMRCRateCache()
    parser = FlexQueryParser(flex_path, rate_cache)
    gen = TrialBalanceGenerator(parser, rate_cache, period)
    gen.process()
    if owners_loan_path and owners_loan_path.exists():
        apply_owners_loan(gen, owners_loan_path, period)
    out = {}
    for code, acc in gen.accounts.items():
        bal = acc.debit - acc.credit
        if bal != 0:
            out[code] = Decimal(str(round(bal, 2)))
    return out


def format_reconciliation_report(
    rec: dict,
    flex_path: Path,
    period_end: str,
    qbo_accounts_path: Path | None,
    qbo_date_path: Path | None,
) -> str:
    """Turn reconciliation data dict into plain-text report."""
    lines = []
    lines.append("=" * 60)
    lines.append("Reconciliation: Trial Balance (IBKR) vs QuickBooks")
    lines.append("=" * 60)
    lines.append(f"Period end: {period_end}")
    lines.append(f"Flex: {flex_path}")
    lines.append(f"QBO bank: {qbo_accounts_path}")
    lines.append(f"QBO transactions: {qbo_date_path}")
    lines.append("")

    lines.append("--- Bank reconciliation ---")
    lines.append(f"Book cash (1100+1101+1102+1103): {rec['book_cash']:>15,.2f}")
    lines.append(f"QBO bank (end Balance):         {rec['qbo_bal']:>15,.2f}")
    lines.append(f"Difference:                     {rec['diff_bank']:>15,.2f}")
    if rec["reconciled_bank"]:
        lines.append("  -> Bank reconciled.")
    else:
        lines.append("  -> Unreconciled. Note: Book cash is IBKR cash (1101); QBO is linked bank.")
        lines.append("     Match only if same account; else compare IBKR vs bank separately.")
    lines.append("")

    lines.append("--- Expense alignment ---")
    lines.append(f"Book expenses (5200+5300+5600):  {rec['book_exp']:>15,.2f}")
    lines.append(f"QBO outflows (sum |negative Amt|): {abs(rec['qbo_exp_sum']):>15,.2f}")
    lines.append(f"Difference:                     {rec['diff_exp']:>15,.2f}")
    if rec["aligned_exp"]:
        lines.append("  -> Expenses aligned (within £1).")
    else:
        lines.append("  -> Variance. Book = IBKR fees/interest only; QBO = all outflows in period.")
        lines.append("     Ensure Cash basis and same period; filter QBO by account if needed.")
    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def run_reconciliation(
    flex_path: Path,
    period_end: str,
    qbo_accounts_path: Path,
    qbo_date_path: Path,
    out_path: Path | None,
    owners_loan_path: Path | None = None,
) -> str:
    """Build reconciliation report (text)."""
    book = get_book_figures(flex_path, period_end, owners_loan_path)
    if book is None:
        return (
            "WARNING: Could not run trial balance pipeline. Book figures unavailable.\n"
            "Install dependencies and ensure scripts/ibkr_trial_balance.py is runnable."
        )

    book_cash = (
        book.get("1100", Decimal("0"))
        + book.get("1101", Decimal("0"))
        + book.get("1102", Decimal("0"))
        + book.get("1103", Decimal("0"))
    )
    book_exp = (
        book.get("5200", Decimal("0")) + book.get("5300", Decimal("0")) + book.get("5600", Decimal("0"))
    )
    rec = get_reconciliation_data(book_cash, book_exp, qbo_accounts_path, qbo_date_path)
    report = format_reconciliation_report(rec, flex_path, period_end, qbo_accounts_path, qbo_date_path)
    if out_path:
        out_path.write_text(report, encoding="utf-8")
    return report


def main():
    ap = argparse.ArgumentParser(description="Reconcile trial balance with QuickBooks exports")
    ap.add_argument("--flex", type=Path, default=REPO_ROOT / "analysis" / "business.csv", help="IBKR Flex CSV")
    ap.add_argument("--period-end", default="2026-02-28", help="Period end YYYY-MM-DD")
    ap.add_argument("--owners-loan", type=Path, default=None, help="Owner's loan Excel (Date, Account, Amount) for 1103/2101")
    ap.add_argument("--qbo-accounts", type=Path, default=REPO_ROOT / "analysis" / "qbo_accounts.xlsx", help="QBO Transaction Detail by Account")
    ap.add_argument("--qbo-date", type=Path, default=REPO_ROOT / "analysis" / "qbo_date.xlsx", help="QBO Transaction List by Date")
    ap.add_argument("--output", "-o", type=Path, default=REPO_ROOT / "analysis" / "reconciliation_report.txt", help="Output report path")
    args = ap.parse_args()

    if not args.flex.exists():
        print(f"Error: Flex file not found: {args.flex}", file=sys.stderr)
        sys.exit(1)
    if not args.qbo_accounts.exists():
        print(f"Warning: QBO accounts file not found: {args.qbo_accounts}", file=sys.stderr)
    if not args.qbo_date.exists():
        print(f"Warning: QBO date file not found: {args.qbo_date}", file=sys.stderr)

    report = run_reconciliation(
        args.flex,
        args.period_end,
        args.qbo_accounts,
        args.qbo_date,
        args.output,
        args.owners_loan,
    )
    print(report)
    if args.output:
        print(f"\nReport saved to: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
