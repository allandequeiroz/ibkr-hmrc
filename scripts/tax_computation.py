#!/usr/bin/env python3
"""
UK Corporation Tax computation for investment holding companies.

Consumes trial balance accounts and Section 104 disposal summary to compute
taxable profit, Corporation Tax liability, and CT600 box mapping.

References:
- HMRC CT600, Rates and Allowances 2025-26
- Dividend exemption, management expenses, ICR (interest) restriction
"""

import csv
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional

# Allow import of section_104_pooling when run from repo root or scripts/
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from section_104_pooling import Section104Pool


@dataclass
class TaxAdjustment:
    """Single adjustment line for tax computation."""
    description: str
    amount: Decimal
    adjustment_type: str  # 'add_back', 'deduct', 'exempt', etc.


@dataclass
class InterestReliefResult:
    """Result of interest relief calculation (ICR-restricted)."""
    total_interest_paid: Decimal
    allowable_interest: Decimal
    disallowed_interest: Decimal
    icr_limit: Decimal
    taxable_earnings: Decimal
    icr_applicable: bool
    warning: Optional[str] = None


@dataclass
class CT600Mapping:
    """CT600 form box mapping."""
    box_13_non_trading_profits: Decimal
    box_16_chargeable_gains: Decimal
    box_46_taxable_total_profit: Decimal
    box_500_corporation_tax: Decimal


class TaxComputation:
    """
    Tax computation engine: taxable profit and Corporation Tax liability.

    Uses trial balance accounts and Section 104 capital gains. Assumes
    dividend exemption, no SSE, management expense relief, ICR on interest.
    """

    # Account codes used
    DIVIDEND_INCOME = '4000'
    INTEREST_RECEIVED = '4100'
    BROKER_FEES = '5200'
    INTEREST_PAID = '5600'

    def __init__(
        self,
        generator: Any,
        section_104_pool: Section104Pool,
        management_expenses_path: Optional[Path] = None,
    ) -> None:
        """
        generator: object with .accounts (dict[str, account]) where account
                   has .debit and .credit (Decimal).
        section_104_pool: Section104Pool after flush_all_pending().
        management_expenses_path: path to CSV of management/deductible expenses (description, amount_gbp, date). Include all allowable expenses not in the trial balance.
        """
        self._accounts = generator.accounts
        self._section_104 = section_104_pool
        self._management_expenses_path = Path(management_expenses_path) if management_expenses_path else None
        self._adjustments: list[TaxAdjustment] = []
        self._interest_relief: Optional[InterestReliefResult] = None
        self._taxable_profit: Optional[Decimal] = None
        self._corporation_tax: Optional[Decimal] = None
        self._ct600: Optional[CT600Mapping] = None

    def _acc(self, code: str) -> Any:
        """Get account by code; return object with .debit, .credit."""
        return self._accounts.get(code)

    def _debit(self, code: str) -> Decimal:
        acc = self._acc(code)
        return acc.debit if acc else Decimal('0')

    def _credit(self, code: str) -> Decimal:
        acc = self._acc(code)
        return acc.credit if acc else Decimal('0')

    def calculate_dividend_exemption(self) -> Decimal:
        """Dividend income (exempt from Corporation Tax)."""
        return self._credit(self.DIVIDEND_INCOME)

    def calculate_capital_gains(self) -> Decimal:
        """Net capital gains from Section 104 disposals (for CT600)."""
        return self._section_104.get_net_capital_gains()

    def _load_additional_management_expenses(self) -> Decimal:
        """Sum of additional management expenses from CSV."""
        total = Decimal('0')
        if not self._management_expenses_path or not self._management_expenses_path.exists():
            return total
        try:
            with open(self._management_expenses_path, 'r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    amt = row.get('amount_gbp', row.get('amount', '0')).strip().replace(',', '')
                    if amt:
                        total += Decimal(amt)
        except (OSError, csv.Error, ValueError):
            pass
        return total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def calculate_management_expenses(self) -> tuple[Decimal, Decimal]:
        """(IBKR fees from TB, additional from CSV)."""
        ibkr = self._debit(self.BROKER_FEES)
        other = self._load_additional_management_expenses()
        return ibkr, other

    def calculate_interest_relief(self) -> InterestReliefResult:
        """
        Allowable interest relief with ICR restriction.

        ICR: interest deduction limited to 30% of taxable earnings (EBITDA proxy).
        For investment company: taxable_earnings = interest_received - management_expenses.

        WARNING: ICR may not apply to investment companies. Seek professional tax advice.
        """
        interest_paid = self._debit(self.INTEREST_PAID)
        if interest_paid == 0:
            return InterestReliefResult(
                total_interest_paid=Decimal('0'),
                allowable_interest=Decimal('0'),
                disallowed_interest=Decimal('0'),
                icr_limit=Decimal('0'),
                taxable_earnings=Decimal('0'),
                icr_applicable=False,
            )

        interest_received = self._credit(self.INTEREST_RECEIVED)
        mgmt_ibkr, mgmt_other = self.calculate_management_expenses()
        management_expenses = mgmt_ibkr + mgmt_other
        taxable_earnings = interest_received - management_expenses

        if taxable_earnings <= 0:
            return InterestReliefResult(
                total_interest_paid=interest_paid,
                allowable_interest=Decimal('0'),
                disallowed_interest=interest_paid,
                icr_limit=Decimal('0'),
                taxable_earnings=taxable_earnings,
                icr_applicable=True,
                warning='ICR calculation may not apply to investment companies. Seek professional tax advice.',
            )

        icr_limit = (taxable_earnings * Decimal('0.30')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        if interest_paid <= icr_limit:
            allowable = interest_paid
            disallowed = Decimal('0')
        else:
            allowable = icr_limit
            disallowed = interest_paid - icr_limit

        self._interest_relief = InterestReliefResult(
            total_interest_paid=interest_paid,
            allowable_interest=allowable,
            disallowed_interest=disallowed,
            icr_limit=icr_limit,
            taxable_earnings=taxable_earnings,
            icr_applicable=True,
            warning='ICR calculation may not apply to investment companies. Seek professional tax advice.',
        )
        return self._interest_relief

    def _get_accounting_profit(self) -> Decimal:
        """Profit per accounts (before tax) from trial balance P&L."""
        income = (
            self._credit('4000') - self._debit('4000')
            + self._credit('4100') - self._debit('4100')
            + self._credit('4200') - self._debit('4200')
            + self._credit('4300') - self._debit('4300')
        )
        expenses = (
            self._debit('5000') - self._credit('5000')
            + self._debit('5100') - self._credit('5100')
            + self._debit('5200') - self._credit('5200')
            + self._debit('5300') - self._credit('5300')
            + self._debit('5400') - self._credit('5400')
            + self._debit('5500') - self._credit('5500')
            + self._debit('5600') - self._credit('5600')
        )
        return (income - expenses).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    def calculate_taxable_profit(self) -> Decimal:
        """
        Total taxable profit (non-trading + chargeable gains).

        Non-trading: interest received - management expenses - allowable interest.
        Capital gains: Section 104 net gains (no SSE assumed).
        """
        self._adjustments = []

        # Dividend exemption (excluded from taxable; for reconciliation only)
        dividend_income = self.calculate_dividend_exemption()
        self._adjustments.append(TaxAdjustment(
            'Dividend income (exempt)',
            dividend_income,
            'exempt',
        ))

        # Non-trading income
        interest_income = self._credit(self.INTEREST_RECEIVED)
        mgmt_ibkr, mgmt_other = self.calculate_management_expenses()
        interest_relief = self.calculate_interest_relief()
        allowable_interest = interest_relief.allowable_interest

        taxable_non_trading = (
            interest_income
            - mgmt_ibkr
            - mgmt_other
            - allowable_interest
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # Capital gains (Section 104; no SSE)
        capital_gains = self.calculate_capital_gains()
        self._adjustments.append(TaxAdjustment(
            'Capital gains (Section 104)',
            capital_gains,
            'chargeable_gains',
        ))

        self._taxable_profit = (taxable_non_trading + capital_gains).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        return self._taxable_profit

    def calculate_corporation_tax(self, taxable_profit: Optional[Decimal] = None) -> Decimal:
        """
        Corporation Tax liability (2025-26 rates).

        Small profits: 19% up to £50,000.
        Main rate: 25% over £250,000.
        Marginal relief: 3/200 for profits between £50k–£250k.
        """
        profit = taxable_profit if taxable_profit is not None else self._taxable_profit
        if profit is None:
            profit = self.calculate_taxable_profit()
        if profit <= 0:
            self._corporation_tax = Decimal('0')
            return self._corporation_tax

        if profit <= 50000:
            tax_liability = profit * Decimal('0.19')
        elif profit >= 250000:
            tax_liability = profit * Decimal('0.25')
        else:
            tax_at_main = profit * Decimal('0.25')
            marginal_relief = (Decimal('250000') - profit) * Decimal('3') / Decimal('200')
            tax_liability = tax_at_main - marginal_relief

        self._corporation_tax = tax_liability.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return self._corporation_tax

    def generate_ct600_mapping(self) -> CT600Mapping:
        """Map computed figures to CT600 boxes."""
        if self._taxable_profit is None:
            self.calculate_taxable_profit()
        if self._corporation_tax is None:
            self.calculate_corporation_tax()

        interest_income = self._credit(self.INTEREST_RECEIVED)
        mgmt_ibkr, mgmt_other = self.calculate_management_expenses()
        interest_relief = self.calculate_interest_relief()
        allowable_interest = interest_relief.allowable_interest

        non_trading = (
            interest_income - mgmt_ibkr - mgmt_other - allowable_interest
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        chargeable_gains = self.calculate_capital_gains()
        taxable_total = self._taxable_profit
        ct_chargeable = self._corporation_tax

        self._ct600 = CT600Mapping(
            box_13_non_trading_profits=non_trading,
            box_16_chargeable_gains=chargeable_gains,
            box_46_taxable_total_profit=taxable_total,
            box_500_corporation_tax=ct_chargeable,
        )
        return self._ct600

    # --- Accessors for report generation ---

    @property
    def adjustments(self) -> list[TaxAdjustment]:
        return list(self._adjustments)

    @property
    def interest_relief_result(self) -> Optional[InterestReliefResult]:
        return self._interest_relief

    @property
    def taxable_profit(self) -> Optional[Decimal]:
        return self._taxable_profit

    @property
    def corporation_tax(self) -> Optional[Decimal]:
        return self._corporation_tax

    @property
    def ct600_mapping(self) -> Optional[CT600Mapping]:
        return self._ct600

    def get_effective_tax_rate(self) -> Optional[Decimal]:
        """Effective Corporation Tax rate (tax / taxable profit)."""
        if self._corporation_tax is None or self._taxable_profit is None or self._taxable_profit <= 0:
            return None
        return (self._corporation_tax / self._taxable_profit).quantize(
            Decimal('0.0001'), rounding=ROUND_HALF_UP
        )

    def get_disposal_summary(self) -> list[Any]:
        """Section 104 disposals (for schedule)."""
        return self._section_104.get_disposal_summary()

    def get_pool_summary(self) -> list[Any]:
        """Section 104 pool summary (for schedule)."""
        return self._section_104.get_pool_summary()


# ---------------------------------------------------------------------------
# Simple test (run with: python tax_computation.py)
# ---------------------------------------------------------------------------

def _make_mock_accounts(
    dividend: Decimal = Decimal('780.13'),
    interest_received: Decimal = Decimal('1604.52'),
    broker_fees: Decimal = Decimal('1120.26'),
    interest_paid: Decimal = Decimal('8743.42'),
) -> dict[str, Any]:
    """Minimal mock accounts for testing."""
    from types import SimpleNamespace
    def acc(d: Decimal, c: Decimal) -> Any:
        return SimpleNamespace(debit=d, credit=c)
    return {
        '4000': acc(Decimal('0'), dividend),
        '4100': acc(Decimal('0'), interest_received),
        '5200': acc(broker_fees, Decimal('0')),
        '5600': acc(interest_paid, Decimal('0')),
        '4200': acc(Decimal('0'), Decimal('0')),
        '4300': acc(Decimal('0'), Decimal('0')),
        '5000': acc(Decimal('0'), Decimal('0')),
        '5100': acc(Decimal('0'), Decimal('0')),
        '5300': acc(Decimal('0'), Decimal('0')),
        '5400': acc(Decimal('0'), Decimal('0')),
        '5500': acc(Decimal('0'), Decimal('0')),
    }


def _test_tax_computation() -> None:
    """Test tax computation with mock data and Section 104 pool."""
    pool = Section104Pool()
    pool.add_acquisition(date(2025, 6, 1), 'AAPL', Decimal('100'), Decimal('15000'))
    pool.remove_disposal(date(2025, 7, 1), 'AAPL', Decimal('100'), Decimal('18000'))
    pool.flush_all_pending()
    assert pool.get_net_capital_gains() == Decimal('3000')

    generator = type('Gen', (), {'accounts': _make_mock_accounts()})()
    tc = TaxComputation(generator, pool)
    div = tc.calculate_dividend_exemption()
    assert div == Decimal('780.13')
    gains = tc.calculate_capital_gains()
    assert gains == Decimal('3000')
    mgmt_ibkr, mgmt_other = tc.calculate_management_expenses()
    assert mgmt_ibkr == Decimal('1120.26')
    assert mgmt_other == Decimal('0')

    taxable = tc.calculate_taxable_profit()
    # Non-trading: 1604.52 - 1120.26 - allowable_interest. ICR: taxable_earnings = 1604.52 - 1120.26 = 484.26, limit = 145.28, so allowable = 145.28
    # taxable_non_trading = 1604.52 - 1120.26 - 145.28 = 338.98, + 3000 = 3338.98
    assert taxable > 0
    ct = tc.calculate_corporation_tax()
    assert ct > 0
    mapping = tc.generate_ct600_mapping()
    assert mapping.box_46_taxable_total_profit == taxable
    assert mapping.box_500_corporation_tax == ct
    print("_test_tax_computation: OK")


if __name__ == '__main__':
    _test_tax_computation()
    print("All tax_computation tests passed.")
