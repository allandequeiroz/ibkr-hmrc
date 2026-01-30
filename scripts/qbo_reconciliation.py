"""
QuickBooks reconciliation: load QBO exports and compute comparison to book figures.

Used by:
- ibkr_trial_balance.py: embed reconciliation section in the HTML report when --qbo-accounts / --qbo-date are passed.
- reconcile_qbo.py: standalone CLI that prints/writes the same reconciliation as text.

Book figures (cash 1100+1101+1102+1103, expenses 5200+5300+5600) come from the caller;
this module only loads QBO data and computes differences.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd


def load_qbo_accounts(path: Path | None) -> pd.DataFrame | None:
    """Load qbo_accounts.xlsx (Transaction Detail by Account). Header on row 4."""
    if path is None or not path.exists():
        return None
    df = pd.read_excel(path, sheet_name=0, header=4)
    if "Transaction date" in df.columns:
        df = df[df["Transaction date"].notna()].copy()
    else:
        col1 = df.columns[1]
        df = df[df[col1].notna()].copy()
    return df


def load_qbo_date(path: Path | None) -> pd.DataFrame | None:
    """Load qbo_date.xlsx (Transaction List by Date). Header on row 4."""
    if path is None or not path.exists():
        return None
    df = pd.read_excel(path, sheet_name=0, header=4)
    if "Date" in df.columns:
        df = df[df["Date"].notna()].copy()
    return df


def qbo_bank_balance(df: pd.DataFrame | None) -> tuple[Decimal, Decimal]:
    """Sum of Amount and last Balance from Transaction Detail by Account. Returns (amt_sum, end_balance)."""
    if df is None or df.empty:
        return Decimal("0"), Decimal("0")
    amt_col = "Amount" if "Amount" in df.columns else df.columns[df.columns.str.contains("amount", case=False)][0]
    amt = df[amt_col].fillna(0).astype(float).sum()
    bal_col = "Balance" if "Balance" in df.columns else None
    if bal_col and bal_col in df.columns:
        last_bal = df[bal_col].dropna()
        end_bal = float(last_bal.iloc[-1]) if len(last_bal) else 0.0
    else:
        end_bal = amt
    return Decimal(str(round(amt, 2))), Decimal(str(round(end_bal, 2)))


def qbo_expense_total(df: pd.DataFrame | None) -> Decimal:
    """Sum of negative Amounts (expenses) from Transaction List by Date."""
    if df is None or df.empty:
        return Decimal("0")
    amt_col = "Amount" if "Amount" in df.columns else df.columns[df.columns.str.contains("amount", case=False)][0]
    expenses = df[df[amt_col] < 0][amt_col].sum()
    return Decimal(str(round(float(expenses), 2)))


def get_reconciliation_data(
    book_cash: Decimal,
    book_exp: Decimal,
    qbo_accounts_path: Path | None,
    qbo_date_path: Path | None,
) -> dict[str, Any]:
    """
    Load QBO exports (when paths given) and compute reconciliation vs book figures.

    Returns a dict: book_cash, book_exp, qbo_bal, qbo_exp_sum, diff_bank, diff_exp,
    reconciled_bank (bool), aligned_exp (bool), has_qbo_bank (bool), has_qbo_date (bool).
    """
    df_accounts = load_qbo_accounts(qbo_accounts_path)
    df_date = load_qbo_date(qbo_date_path)
    qbo_amt, qbo_bal = qbo_bank_balance(df_accounts)
    qbo_exp_sum = qbo_expense_total(df_date)

    diff_bank = book_cash - qbo_bal
    diff_exp = book_exp - abs(qbo_exp_sum)
    reconciled_bank = abs(diff_bank) < Decimal("0.01")
    aligned_exp = abs(diff_exp) < Decimal("1")

    return {
        "book_cash": book_cash,
        "book_exp": book_exp,
        "qbo_bal": qbo_bal,
        "qbo_exp_sum": qbo_exp_sum,
        "diff_bank": diff_bank,
        "diff_exp": diff_exp,
        "reconciled_bank": reconciled_bank,
        "aligned_exp": aligned_exp,
        "has_qbo_bank": df_accounts is not None and not df_accounts.empty,
        "has_qbo_date": df_date is not None and not df_date.empty,
    }
