#!/usr/bin/env python3
"""
Section 104 Share Pooling for UK Corporation Tax CGT Calculations.

Implements UK share identification rules (same-day, 30-day, Section 104 pool)
per HMRC Capital Gains Manual. Used for CT600 capital gains computation;
financial statements continue to use FIFO (see ibkr_trial_balance.py).

References:
- HMRC CG51555, CG51570, CG51620
- Share identification order: same-day -> 30-day -> Section 104 pool
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import sys
from typing import Optional

# Asset classes that use Section 104 for tax (STK, OPT; exclude CASH/CRYPTO for tax)
SECTION_104_ASSET_CLASSES = frozenset(('STK', 'OPT'))


@dataclass
class DisposalRecord:
    """A disposal (or unmatched portion) awaiting same-day/30-day matching."""
    date: date
    symbol: str
    qty_remaining: Decimal
    original_qty: Decimal
    total_proceeds_gbp: Decimal

    @property
    def proceeds_per_unit(self) -> Decimal:
        if self.original_qty == 0:
            return Decimal('0')
        return (self.total_proceeds_gbp / self.original_qty).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )


@dataclass
class MatchedDisposal:
    """A completed disposal with cost and gain/loss (for reporting)."""
    date: date
    symbol: str
    quantity: Decimal
    proceeds_gbp: Decimal
    cost_gbp: Decimal
    gain_loss_gbp: Decimal
    matching_rule: str  # 'same_day', 'thirty_day', 'section_104'


@dataclass
class PoolSummary:
    """Current Section 104 pool position for a symbol."""
    symbol: str
    quantity: Decimal
    cost_gbp: Decimal

    @property
    def avg_cost_per_unit(self) -> Decimal:
        if self.quantity == 0:
            return Decimal('0')
        return (self.cost_gbp / self.quantity).quantize(
            Decimal('0.0001'), rounding=ROUND_HALF_UP
        )


class Section104Pool:
    """
    Section 104 share pooling engine with same-day and 30-day matching.

    Share identification order (UK CGT):
    1. Same-day acquisitions
    2. Acquisitions within 30 days after disposal (bed and breakfast)
    3. Section 104 pool (average cost)
    """

    THIRTY_DAYS = timedelta(days=30)

    def __init__(self) -> None:
        # Section 104 pools: symbol -> {qty, cost}
        self._pools: dict[str, dict[str, Decimal]] = defaultdict(
            lambda: {'qty': Decimal('0'), 'cost': Decimal('0')}
        )
        # Pending disposals not yet matched: list of DisposalRecord
        # Ordered by disposal date so we flush oldest first
        self._pending_disposals: list[DisposalRecord] = []
        # Completed disposals for reporting
        self._disposals: list[MatchedDisposal] = []

    def add_acquisition(
        self,
        acq_date: date,
        symbol: str,
        qty: Decimal,
        cost_gbp: Decimal,
    ) -> None:
        """
        Add an acquisition. Match first against pending disposals (same-day
        then 30-day); remainder goes to Section 104 pool.
        """
        if qty <= 0:
            return
        remaining_qty = qty
        remaining_cost = cost_gbp
        cost_per_unit = (cost_gbp / qty).quantize(
            Decimal('0.0001'), rounding=ROUND_HALF_UP
        ) if qty else Decimal('0')

        # Match against pending disposals: same-day first, then 30-day (earliest disposal first)
        same_day = [
            (i, d) for i, d in enumerate(self._pending_disposals)
            if d.symbol == symbol and d.date == acq_date
        ]
        thirty_day = [
            (i, d) for i, d in enumerate(self._pending_disposals)
            if d.symbol == symbol
            and d.date < acq_date
            and (acq_date - d.date) <= self.THIRTY_DAYS
            and (i, d) not in [(x, y) for x, y in same_day]
        ]
        thirty_day.sort(key=lambda x: x[1].date)

        # Process same-day then 30-day
        to_match: list[tuple[int, DisposalRecord]] = same_day + thirty_day

        for _idx, disp in to_match:
            if remaining_qty <= 0 or disp.qty_remaining <= 0:
                continue
            match_qty = min(remaining_qty, disp.qty_remaining)
            match_cost = (cost_per_unit * match_qty).quantize(
                Decimal('0.01'), rounding=ROUND_HALF_UP
            )
            match_proceeds = (
                disp.total_proceeds_gbp * match_qty / disp.original_qty
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            rule = 'same_day' if disp.date == acq_date else 'thirty_day'

            self._disposals.append(MatchedDisposal(
                date=disp.date,
                symbol=symbol,
                quantity=match_qty,
                proceeds_gbp=match_proceeds,
                cost_gbp=match_cost,
                gain_loss_gbp=match_proceeds - match_cost,
                matching_rule=rule,
            ))
            disp.qty_remaining -= match_qty
            remaining_qty -= match_qty
            remaining_cost -= match_cost

        # Remove fully matched pending disposals
        self._pending_disposals = [
            d for d in self._pending_disposals
            if d.qty_remaining > 0
        ]

        # Remainder of acquisition goes to Section 104 pool
        if remaining_qty > 0:
            pool = self._pools[symbol]
            pool['qty'] += remaining_qty
            pool['cost'] += remaining_cost

    def _flush_pending_disposals_for_symbol(
        self, symbol: str, before_date: date
    ) -> None:
        """
        For pending disposals of symbol with disposal_date + 30 < before_date,
        take unmatched portion from Section 104 pool and record.
        """
        pool = self._pools[symbol]
        new_pending: list[DisposalRecord] = []

        for disp in self._pending_disposals:
            if disp.symbol != symbol or disp.qty_remaining <= 0:
                new_pending.append(disp)
                continue
            if (disp.date + self.THIRTY_DAYS) >= before_date:
                new_pending.append(disp)
                continue

            # Flush this disposal from pool
            qty_to_take = disp.qty_remaining
            if pool['qty'] <= 0:
                # FIFO failure: no shares in pool (phantom gain)
                cost_gbp = Decimal('0')
                print(
                    f"Warning: Section 104 flush {qty_to_take} {symbol} but pool "
                    f"empty. Using zero cost.",
                    file=sys.stderr,
                )
            else:
                avg_cost = pool['cost'] / pool['qty']
                cost_gbp = (avg_cost * qty_to_take).quantize(
                    Decimal('0.01'), rounding=ROUND_HALF_UP
                )
                pool['cost'] -= cost_gbp
                pool['qty'] -= qty_to_take
                if pool['qty'] < 0:
                    pool['qty'] = Decimal('0')
                if pool['cost'] < 0:
                    pool['cost'] = Decimal('0')

            proceeds = (
                disp.total_proceeds_gbp * qty_to_take / disp.original_qty
            ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self._disposals.append(MatchedDisposal(
                date=disp.date,
                symbol=symbol,
                quantity=qty_to_take,
                proceeds_gbp=proceeds,
                cost_gbp=cost_gbp,
                gain_loss_gbp=proceeds - cost_gbp,
                matching_rule='section_104',
            ))

        self._pending_disposals = new_pending

    def remove_disposal(
        self,
        disp_date: date,
        symbol: str,
        qty: Decimal,
        proceeds_gbp: Decimal,
    ) -> None:
        """
        Record a disposal. First flush any pending disposals for this symbol
        that are past the 30-day window. Then add this disposal to pending
        (it will be matched by future acquisitions or flushed at end).
        """
        if qty <= 0:
            return
        # Flush pending disposals for this symbol that are now past 30 days
        self._flush_pending_disposals_for_symbol(symbol, disp_date)

        self._pending_disposals.append(DisposalRecord(
            date=disp_date,
            symbol=symbol,
            qty_remaining=qty,
            original_qty=qty,
            total_proceeds_gbp=proceeds_gbp,
        ))

    def flush_all_pending(self) -> None:
        """
        Call after all trades processed. Flush all pending disposals
        (take from Section 104 pool).
        """
        # Process by symbol and by disposal date to avoid index issues
        symbols = set(d.symbol for d in self._pending_disposals)
        for symbol in symbols:
            self._flush_pending_disposals_for_symbol(
                symbol, date(9999, 12, 31)
            )

    def get_pool_summary(self) -> list[PoolSummary]:
        """Current Section 104 pool holdings (qty and cost per symbol)."""
        result: list[PoolSummary] = []
        for symbol in sorted(self._pools.keys()):
            p = self._pools[symbol]
            if p['qty'] > 0:
                result.append(PoolSummary(
                    symbol=symbol,
                    quantity=p['qty'],
                    cost_gbp=p['cost'],
                ))
        return result

    def get_disposal_summary(self) -> list[MatchedDisposal]:
        """All disposals with gain/loss (for tax computation)."""
        return list(self._disposals)

    def get_net_capital_gains(self) -> Decimal:
        """Sum of gain/loss across all disposals."""
        return sum(
            d.gain_loss_gbp for d in self._disposals
        ).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Simple tests (run with: python section_104_pooling.py)
# ---------------------------------------------------------------------------

def _test_section_104_only() -> None:
    """Test pure Section 104 pooling (no same-day/30-day)."""
    pool = Section104Pool()
    d = date(2025, 6, 1)
    pool.add_acquisition(d, 'AAPL', Decimal('100'), Decimal('15000'))
    pool.add_acquisition(date(2025, 6, 15), 'AAPL', Decimal('50'), Decimal('8000'))
    pool.remove_disposal(date(2025, 7, 1), 'AAPL', Decimal('75'), Decimal('13500'))
    pool.flush_all_pending()
    summary = pool.get_pool_summary()
    assert len(summary) == 1
    assert summary[0].symbol == 'AAPL'
    assert summary[0].quantity == Decimal('75')
    # Pool cost: 15000 + 8000 = 23000, qty 150. Cost of 75 = 11500
    assert summary[0].cost_gbp == Decimal('11500')
    disposals = pool.get_disposal_summary()
    assert len(disposals) == 1
    assert disposals[0].cost_gbp == Decimal('11500')
    assert disposals[0].proceeds_gbp == Decimal('13500')
    assert disposals[0].gain_loss_gbp == Decimal('2000')
    assert disposals[0].matching_rule == 'section_104'
    print("_test_section_104_only: OK")


def _test_same_day_matching() -> None:
    """Test same-day acquisition matches disposal first."""
    pool = Section104Pool()
    d = date(2025, 6, 10)
    # Disposal first (in real flow we'd have added acquisition same day before)
    pool.remove_disposal(d, 'XYZ', Decimal('100'), Decimal('11000'))
    pool.add_acquisition(d, 'XYZ', Decimal('100'), Decimal('9000'))
    pool.flush_all_pending()
    disposals = pool.get_disposal_summary()
    assert len(disposals) == 1
    assert disposals[0].matching_rule == 'same_day'
    assert disposals[0].cost_gbp == Decimal('9000')
    assert disposals[0].gain_loss_gbp == Decimal('2000')
    assert len(pool.get_pool_summary()) == 0
    print("_test_same_day_matching: OK")


def _test_thirty_day_matching() -> None:
    """Test 30-day (bed and breakfast) matching: disposal then acquisition 14 days later."""
    pool = Section104Pool()
    pool.remove_disposal(date(2025, 6, 1), 'ABC', Decimal('50'), Decimal('6000'))
    pool.add_acquisition(date(2025, 6, 15), 'ABC', Decimal('50'), Decimal('4000'))
    pool.flush_all_pending()
    disposals = pool.get_disposal_summary()
    assert len(disposals) == 1
    assert disposals[0].matching_rule == 'thirty_day'
    assert disposals[0].quantity == Decimal('50')
    assert disposals[0].cost_gbp == Decimal('4000')
    assert disposals[0].proceeds_gbp == Decimal('6000')
    assert disposals[0].gain_loss_gbp == Decimal('2000')
    assert len(pool.get_pool_summary()) == 0
    print("_test_thirty_day_matching: OK")


if __name__ == '__main__':
    _test_section_104_only()
    _test_same_day_matching()
    _test_thirty_day_matching()
    print("All section_104_pooling tests passed.")
