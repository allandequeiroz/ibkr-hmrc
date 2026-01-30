#!/usr/bin/env python3
"""
IBKR Flex Query to UK Trial Balance Reconciliation Tool
For FRS 105 micro-entity: Historical cost basis, GBP functional currency

Usage:
    python ibkr_trial_balance.py <flex_query.csv> --period-end YYYY-MM-DD [--company NAME] [--output PATH]
    [--management-expenses PATH] [--qbo-accounts PATH] [--qbo-date PATH]

Full report (trial balance + tax + QuickBooks reconciliation) in one command: pass --qbo-accounts
and --qbo-date with your QBO export paths (Transaction Detail by Account, Transaction List by Date).
See docs/QUICKBOOKS_EXPORT.md for export steps.

Requirements:
    pip install pandas requests --break-system-packages
"""

import argparse
import csv
import io
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional, Any
import requests

try:
    import pandas as pd
except ImportError:
    pd = None  # owners_loan.xlsx requires pandas

# Tax computation (Section 104 + CT): allow import when run from repo root or scripts/
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
try:
    from section_104_pooling import Section104Pool
    from tax_computation import TaxComputation
except ImportError:
    Section104Pool = None  # type: ignore
    TaxComputation = None  # type: ignore
try:
    from qbo_reconciliation import get_reconciliation_data
except ImportError:
    get_reconciliation_data = None  # type: ignore

# ============================================================================
# HMRC Exchange Rates
# ============================================================================

HMRC_RATE_URL = "https://www.trade-tariff.service.gov.uk/uk/api/exchange_rates/files/monthly_csv_{year}-{month}.csv"

def fetch_hmrc_rates(year: int, month: int) -> dict[str, Decimal]:
    """Fetch HMRC monthly exchange rates for a given month.
    
    Returns dict of currency_code -> units per GBP
    """
    url = HMRC_RATE_URL.format(year=year, month=month)
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch HMRC rates for {year}-{month:02d}: {e}")
    
    rates = {}
    reader = csv.DictReader(io.StringIO(resp.text))
    for row in reader:
        code = row.get('Currency Code', row.get('currency_code', '')).strip()
        rate_str = row.get('Currency Units per £1', row.get('rate', '')).strip()
        if code and rate_str:
            try:
                rates[code] = Decimal(rate_str)
            except:
                pass
    return rates


class HMRCRateCache:
    """Cache for HMRC monthly rates."""
    
    def __init__(self):
        self._cache: dict[tuple[int, int], dict[str, Decimal]] = {}
    
    def get_rate(self, currency: str, tx_date: date) -> Decimal:
        """Get exchange rate for currency on transaction date.
        
        HMRC rates published on penultimate Thursday of prior month,
        apply to the following calendar month.
        """
        if currency == 'GBP':
            return Decimal('1')
        
        key = (tx_date.year, tx_date.month)
        if key not in self._cache:
            self._cache[key] = fetch_hmrc_rates(tx_date.year, tx_date.month)
        
        rates = self._cache[key]
        if currency not in rates:
            raise ValueError(f"No HMRC rate for {currency} in {tx_date.year}-{tx_date.month:02d}")
        
        return rates[currency]
    
    def to_gbp(self, amount: Decimal, currency: str, tx_date: date) -> Decimal:
        """Convert amount to GBP using HMRC rate for transaction month."""
        rate = self.get_rate(currency, tx_date)
        # HMRC rates are "currency units per £1"
        # So GBP = foreign_amount / rate
        return (amount / rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


# ============================================================================
# Data Structures
# ============================================================================

@dataclass
class Trade:
    """A single trade execution."""
    date: date
    symbol: str
    description: str
    buy_sell: str  # 'BUY' or 'SELL'
    quantity: Decimal
    price: Decimal
    proceeds: Decimal  # Net proceeds (positive for sells, negative for buys)
    commission: Decimal
    currency: str
    asset_class: str  # 'STK', 'OPT', 'CASH', 'CRYPTO', etc.
    
    @property
    def is_buy(self) -> bool:
        return self.buy_sell.upper() in ('BUY', 'BOT')
    
    @property
    def is_sell(self) -> bool:
        return self.buy_sell.upper() in ('SELL', 'SLD')


@dataclass
class CashTransaction:
    """A cash transaction (dividend, interest, fee, deposit, etc.)."""
    date: date
    type: str  # 'Dividends', 'Withholding Tax', 'Broker Interest', 'Other Fees', etc.
    symbol: str
    description: str
    amount: Decimal
    currency: str


@dataclass 
class Position:
    """An open position at period end."""
    symbol: str
    description: str
    quantity: Decimal
    cost_basis: Decimal  # Average cost in base currency
    market_value: Decimal
    currency: str


@dataclass
class LotHolding:
    """Tax lot for FIFO cost tracking."""
    date: date
    symbol: str
    quantity: Decimal
    cost_gbp: Decimal  # Total cost in GBP
    asset_class: str = 'STK'  # Asset class for filtering

    @property
    def unit_cost_gbp(self) -> Decimal:
        if self.quantity == 0:
            return Decimal('0')
        return self.cost_gbp / self.quantity


# ============================================================================
# IBKR Flex Query Parser
# ============================================================================

class FlexQueryParser:
    """Parse IBKR Activity Flex Query CSV export."""
    
    def __init__(self, filepath: Path, rate_cache: HMRCRateCache):
        self.filepath = filepath
        self.rate_cache = rate_cache
        self.trades: list[Trade] = []
        self.cash_transactions: list[CashTransaction] = []
        self.positions: list[Position] = []
        self._parse()
    
    def _parse_date(self, date_str: str) -> date:
        """Parse date from various IBKR formats."""
        date_str = date_str.strip()
        for fmt in ['%Y-%m-%d', '%Y%m%d', '%d-%m-%Y', '%m/%d/%Y']:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        raise ValueError(f"Cannot parse date: {date_str}")
    
    def _parse_decimal(self, val: str) -> Decimal:
        """Parse decimal from string, handling commas and empty values."""
        val = val.strip().replace(',', '')
        if not val or val == '--':
            return Decimal('0')
        return Decimal(val)
    
    def _parse(self):
        """Parse the Flex Query CSV file."""
        with open(self.filepath, 'r', encoding='utf-8-sig') as f:
            content = f.read()

        # IBKR Flex Query CSV format:
        # "HEADER","SectionCode","Field1","Field2",...
        # "DATA","SectionCode","Value1","Value2",...

        lines = content.strip().split('\n')
        headers = {}

        for line in lines:
            if not line.strip():
                continue

            # Parse CSV line
            reader = csv.reader(io.StringIO(line))
            row = next(reader)

            if len(row) < 3:
                continue

            line_type = row[0].strip()
            section_code = row[1].strip()

            if line_type == 'HEADER':
                headers[section_code] = row
                continue

            if line_type == 'DATA' and section_code in headers:
                self._parse_row(section_code, headers[section_code], row)
    
    def _parse_row(self, section: str, headers: list[str], row: list[str]):
        """Parse a data row based on section type."""
        # Create dict from headers and row
        data = {}
        for i, h in enumerate(headers):
            if i < len(row):
                data[h.strip()] = row[i].strip()
        
        # Route to appropriate parser
        section_lower = section.lower()
        
        if 'trade' in section_lower or section in ('TRNT', 'Trades'):
            self._parse_trade(data)
        elif 'cash' in section_lower or 'dividend' in section_lower or section in ('STCI', 'CTRN', 'CashReport'):
            self._parse_cash_transaction(data)
        elif 'position' in section_lower or 'open' in section_lower or section in ('OPT', 'POST', 'OpenPositions'):
            self._parse_position(data)
    
    def _parse_trade(self, data: dict):
        """Parse a trade row."""
        # Find the date field
        date_val = None
        for key in ['TradeDate', 'Trade Date', 'DateTime', 'Date/Time', 'Date']:
            if key in data and data[key]:
                date_val = data[key].split(';')[0].split(' ')[0]  # Handle datetime
                break
        
        if not date_val:
            return
        
        try:
            trade = Trade(
                date=self._parse_date(date_val),
                symbol=data.get('Symbol', data.get('symbol', '')),
                description=data.get('Description', data.get('description', '')),
                buy_sell=data.get('Buy/Sell', data.get('BuySell', data.get('Side', ''))),
                quantity=abs(self._parse_decimal(data.get('Quantity', data.get('quantity', '0')))),
                price=self._parse_decimal(data.get('TradePrice', data.get('OrigTradePrice', data.get('Price', data.get('price', '0'))))),
                proceeds=self._parse_decimal(data.get('Proceeds', data.get('proceeds', '0'))),
                commission=abs(self._parse_decimal(data.get('IBCommission', data.get('Commission', data.get('commission', '0'))))),
                currency=data.get('CurrencyPrimary', data.get('Currency', data.get('currency', 'USD'))),
                asset_class=data.get('AssetClass', data.get('assetClass', 'STK')),
            )
            if trade.symbol:
                self.trades.append(trade)
        except (ValueError, KeyError) as e:
            print(f"Warning: Could not parse trade row: {e}", file=sys.stderr)
    
    def _parse_cash_transaction(self, data: dict):
        """Parse a cash transaction row."""
        date_val = None
        for key in ['Date', 'DateTime', 'Date/Time', 'SettleDate', 'ReportDate']:
            if key in data and data[key]:
                date_val = data[key].split(';')[0].split(' ')[0]
                break
        
        if not date_val:
            return
        
        try:
            tx = CashTransaction(
                date=self._parse_date(date_val),
                type=data.get('Type', data.get('type', 'Other')),
                symbol=data.get('Symbol', data.get('symbol', '')),
                description=data.get('Description', data.get('description', '')),
                amount=self._parse_decimal(data.get('Amount', data.get('amount', '0'))),
                currency=data.get('CurrencyPrimary', data.get('Currency', data.get('currency', 'USD'))),
            )
            if tx.amount != 0:
                self.cash_transactions.append(tx)
        except (ValueError, KeyError) as e:
            print(f"Warning: Could not parse cash transaction: {e}", file=sys.stderr)
    
    def _parse_position(self, data: dict):
        """Parse an open position row."""
        try:
            pos = Position(
                symbol=data.get('Symbol', data.get('symbol', '')),
                description=data.get('Description', data.get('description', '')),
                quantity=self._parse_decimal(data.get('Quantity', data.get('Position', '0'))),
                cost_basis=self._parse_decimal(data.get('CostBasisMoney', data.get('CostBasis', '0'))),
                market_value=self._parse_decimal(data.get('PositionValue', data.get('MarkToMarketValue', data.get('MarketValue', '0')))),
                currency=data.get('CurrencyPrimary', data.get('Currency', 'USD')),
            )
            if pos.symbol and pos.quantity != 0:
                self.positions.append(pos)
        except (ValueError, KeyError) as e:
            print(f"Warning: Could not parse position: {e}", file=sys.stderr)


# ============================================================================
# Trial Balance Generator
# ============================================================================

@dataclass
class TrialBalanceAccount:
    """A single account in the trial balance."""
    code: str
    name: str
    debit: Decimal = Decimal('0')
    credit: Decimal = Decimal('0')
    
    @property
    def balance(self) -> Decimal:
        return self.debit - self.credit


class TrialBalanceGenerator:
    """Generate FRS 105 trial balance from IBKR data."""
    
    # Chart of accounts for investment holding company
    ACCOUNTS = {
        # Assets
        '1100': 'Cash at Bank - GBP',
        '1101': 'Cash at Bank - USD',
        '1102': 'Cash at Bank - Other CCY',
        '1103': 'Cash at Bank - Other',  # Barclays / non-IBKR (from owners_loan.xlsx)
        '1200': 'Listed Investments at Cost',
        
        # Liabilities
        '2100': 'Accruals and Deferred Income',
        '2101': "Director's / Owner's Loan",
        
        # Capital
        '3000': 'Share Capital',
        '3100': 'Retained Earnings B/F',
        '3200': 'Profit/(Loss) for Period',
        
        # Income
        '4000': 'Dividend Income (Gross)',
        '4100': 'Bank Interest Received',
        '4200': 'Realized Gains on Investments',
        
        # Expenses
        '5000': 'Foreign Withholding Tax',
        '5100': 'Broker Commissions',
        '5200': 'Broker Fees',
        '5300': 'Bank Charges',
        '5400': 'Realized Losses on Investments',
        '5500': 'Foreign Exchange Losses',
        '5600': 'Interest Paid',
        
        # Contra
        '4300': 'Foreign Exchange Gains',
    }
    
    def __init__(self, parser: FlexQueryParser, rate_cache: HMRCRateCache, period_end: date):
        self.parser = parser
        self.rate_cache = rate_cache
        self.period_end = period_end
        
        # Initialize accounts
        self.accounts: dict[str, TrialBalanceAccount] = {
            code: TrialBalanceAccount(code=code, name=name)
            for code, name in self.ACCOUNTS.items()
        }
        
        # Cost tracking per symbol (FIFO)
        self.holdings: dict[str, list[LotHolding]] = defaultdict(list)
        
        # Section 104 pooling for UK tax (CT600) - STK/OPT only
        self.section_104: Optional[Any] = Section104Pool() if Section104Pool else None
        
        # Detailed journal entries for audit trail
        self.journal_entries: list[dict] = []
    
    def _debit(self, account_code: str, amount: Decimal, memo: str = ''):
        """Record a debit entry."""
        if amount < 0:
            self._credit(account_code, abs(amount), memo)
            return
        self.accounts[account_code].debit += amount
        self.journal_entries.append({
            'account': account_code,
            'debit': amount,
            'credit': Decimal('0'),
            'memo': memo
        })
    
    def _credit(self, account_code: str, amount: Decimal, memo: str = ''):
        """Record a credit entry."""
        if amount < 0:
            self._debit(account_code, abs(amount), memo)
            return
        self.accounts[account_code].credit += amount
        self.journal_entries.append({
            'account': account_code,
            'debit': Decimal('0'),
            'credit': amount,
            'memo': memo
        })
    
    def process(self):
        """Process all transactions and generate trial balance."""
        # Sort trades by date for FIFO, buys before sells within same date.
        # Same-day sells must not precede same-day buys, otherwise FIFO
        # finds no lots and records zero cost (inflating realized gains).
        sorted_trades = sorted(self.parser.trades,
                               key=lambda t: (t.date, 0 if t.is_buy else 1))
        
        for trade in sorted_trades:
            self._process_trade(trade)
            if self.section_104 and trade.asset_class in ('STK', 'OPT'):
                self._process_trade_section_104(trade)
        
        if self.section_104:
            self.section_104.flush_all_pending()
        
        for tx in self.parser.cash_transactions:
            self._process_cash_transaction(tx)
    
    def _process_trade(self, trade: Trade):
        """Process a single trade under FRS 105 historical cost."""
        # Route gains/losses to the correct P&L accounts by asset class.
        # FX conversions (CASH) use FX gain/loss accounts;
        # all others (STK, OPT, CRYPTO) use investment gain/loss accounts.
        if trade.asset_class == 'CASH':
            gain_account = '4300'  # Foreign Exchange Gains
            loss_account = '5500'  # Foreign Exchange Losses
        else:
            gain_account = '4200'  # Realized Gains on Investments
            loss_account = '5400'  # Realized Losses on Investments

        # Convert to GBP at transaction date
        if trade.is_buy:
            # Purchase: Debit Investments, Credit Cash
            # Cost = abs(proceeds) + commission
            cost_foreign = abs(trade.proceeds) + trade.commission
            cost_gbp = self.rate_cache.to_gbp(cost_foreign, trade.currency, trade.date)
            
            # Record cost lot
            lot = LotHolding(
                date=trade.date,
                symbol=trade.symbol,
                quantity=trade.quantity,
                cost_gbp=cost_gbp,
                asset_class=trade.asset_class
            )
            self.holdings[trade.symbol].append(lot)
            
            # Journal entries — commission capitalised in cost per FRS 105
            self._debit('1200', cost_gbp, f"Buy {trade.quantity} {trade.symbol}")
            self._credit('1101', cost_gbp, f"Buy {trade.quantity} {trade.symbol}")
        
        else:  # SELL
            # Disposal: net proceeds = gross proceeds minus sell commission
            net_proceeds_foreign = abs(trade.proceeds) - trade.commission
            net_proceeds_gbp = self.rate_cache.to_gbp(net_proceeds_foreign, trade.currency, trade.date)

            # Cost of shares sold (FIFO) — includes capitalised buy commission
            cost_of_sold = self._calculate_fifo_cost(trade.symbol, trade.quantity)

            # Journal entries
            self._debit('1101', net_proceeds_gbp, f"Sell {trade.quantity} {trade.symbol}")
            self._credit('1200', cost_of_sold, f"Cost of {trade.quantity} {trade.symbol} sold")

            # Gain or loss on disposal
            gain_loss = net_proceeds_gbp - cost_of_sold
            if gain_loss > 0:
                self._credit(gain_account, gain_loss, f"Gain on {trade.symbol}")
            elif gain_loss < 0:
                self._debit(loss_account, abs(gain_loss), f"Loss on {trade.symbol}")
    
    def _process_trade_section_104(self, trade: Trade) -> None:
        """Feed STK/OPT trade to Section 104 pool for UK tax computation."""
        if not self.section_104:
            return
        if trade.is_buy:
            cost_foreign = abs(trade.proceeds) + trade.commission
            cost_gbp = self.rate_cache.to_gbp(cost_foreign, trade.currency, trade.date)
            self.section_104.add_acquisition(trade.date, trade.symbol, trade.quantity, cost_gbp)
        else:
            net_proceeds_foreign = abs(trade.proceeds) - trade.commission
            net_proceeds_gbp = self.rate_cache.to_gbp(net_proceeds_foreign, trade.currency, trade.date)
            self.section_104.remove_disposal(trade.date, trade.symbol, trade.quantity, net_proceeds_gbp)
    
    def _calculate_fifo_cost(self, symbol: str, quantity: Decimal) -> Decimal:
        """Calculate cost of sold shares using FIFO."""
        remaining = quantity
        total_cost = Decimal('0')
        
        lots = self.holdings.get(symbol, [])
        new_lots = []
        
        for lot in lots:
            if remaining <= 0:
                new_lots.append(lot)
                continue
            
            if lot.quantity <= remaining:
                # Consume entire lot
                total_cost += lot.cost_gbp
                remaining -= lot.quantity
            else:
                # Partial lot consumption
                fraction = remaining / lot.quantity
                cost_consumed = (lot.cost_gbp * fraction).quantize(Decimal('0.01'))
                total_cost += cost_consumed
                
                # Remaining lot
                new_lots.append(LotHolding(
                    date=lot.date,
                    symbol=lot.symbol,
                    quantity=lot.quantity - remaining,
                    cost_gbp=lot.cost_gbp - cost_consumed,
                    asset_class=lot.asset_class
                ))
                remaining = Decimal('0')
        
        self.holdings[symbol] = new_lots
        return total_cost
    
    def _process_cash_transaction(self, tx: CashTransaction):
        """Process a cash transaction."""
        amount_gbp = self.rate_cache.to_gbp(abs(tx.amount), tx.currency, tx.date)
        is_credit = tx.amount > 0  # Positive = received
        
        tx_type = tx.type.lower()
        
        if 'dividend' in tx_type and 'withhold' not in tx_type:
            # Dividend received
            self._debit('1101', amount_gbp, f"Dividend {tx.symbol}")
            self._credit('4000', amount_gbp, f"Dividend income {tx.symbol}")
        
        elif 'withhold' in tx_type or 'tax' in tx_type:
            # Withholding tax (negative amount)
            self._debit('5000', amount_gbp, f"WHT {tx.symbol}")
            self._credit('1101', amount_gbp, f"WHT deducted {tx.symbol}")
        
        elif 'interest' in tx_type:
            if is_credit:
                self._debit('1101', amount_gbp, f"Interest received")
                self._credit('4100', amount_gbp, f"Interest income")
            else:
                self._debit('5600', amount_gbp, f"Interest paid")
                self._credit('1101', amount_gbp, f"Interest expense")
        
        elif 'fee' in tx_type or 'commission' in tx_type:
            self._debit('5200', amount_gbp, f"Fee: {tx.description}")
            self._credit('1101', amount_gbp, f"Fee paid")
        
        elif 'deposit' in tx_type or 'transfer' in tx_type:
            if is_credit:
                # Deposit from shareholder (assume capital contribution)
                self._debit('1101', amount_gbp, f"Deposit: {tx.description}")
                self._credit('3000', amount_gbp, f"Capital contribution")
            else:
                # Withdrawal
                self._debit('3000', amount_gbp, f"Capital distribution")
                self._credit('1101', amount_gbp, f"Withdrawal: {tx.description}")
        
        else:
            # Other - classify as fee if negative, other income if positive
            if is_credit:
                self._debit('1101', amount_gbp, f"Other: {tx.description}")
                self._credit('4100', amount_gbp, f"Other income")
            else:
                self._debit('5200', amount_gbp, f"Other: {tx.description}")
                self._credit('1101', amount_gbp, f"Other expense")
    
    def _calculate_retained_earnings(self):
        """Calculate retained earnings as balancing figure."""
        # In a real system, this would come from prior period.
        # For now, calculate P&L and assume zero brought forward.
        
        # Income accounts (credits are positive)
        income = (
            self.accounts['4000'].credit - self.accounts['4000'].debit +
            self.accounts['4100'].credit - self.accounts['4100'].debit +
            self.accounts['4200'].credit - self.accounts['4200'].debit +
            self.accounts['4300'].credit - self.accounts['4300'].debit
        )
        
        # Expense accounts (debits are positive)
        expenses = (
            self.accounts['5000'].debit - self.accounts['5000'].credit +
            self.accounts['5100'].debit - self.accounts['5100'].credit +
            self.accounts['5200'].debit - self.accounts['5200'].credit +
            self.accounts['5300'].debit - self.accounts['5300'].credit +
            self.accounts['5400'].debit - self.accounts['5400'].credit +
            self.accounts['5500'].debit - self.accounts['5500'].credit +
            self.accounts['5600'].debit - self.accounts['5600'].credit
        )
        
        profit_loss = income - expenses
        
        if profit_loss > 0:
            self._credit('3200', profit_loss, "Profit for period")
        else:
            self._debit('3200', abs(profit_loss), "Loss for period")
    
    def get_trial_balance(self) -> list[dict]:
        """Get trial balance as list of account balances."""
        result = []
        for code in sorted(self.accounts.keys()):
            acc = self.accounts[code]
            if acc.debit != 0 or acc.credit != 0:
                result.append({
                    'code': acc.code,
                    'name': acc.name,
                    'debit': acc.debit,
                    'credit': acc.credit,
                })
        return result
    
    def get_holdings_summary(self) -> list[dict]:
        """Get summary of holdings at cost.

        Excludes CASH and CRYPTO asset classes - these are processed for
        gain/loss calculation but are not genuine investment holdings.
        """
        result = []
        for symbol, lots in sorted(self.holdings.items()):
            # Filter out CASH (FX conversions) and CRYPTO (Paxos-custodied)
            investment_lots = [lot for lot in lots if lot.asset_class not in ('CASH', 'CRYPTO')]

            total_qty = sum(lot.quantity for lot in investment_lots)
            total_cost = sum(lot.cost_gbp for lot in investment_lots)

            if total_qty > 0:
                result.append({
                    'symbol': symbol,
                    'quantity': total_qty,
                    'cost_gbp': total_cost,
                    'avg_cost': (total_cost / total_qty).quantize(Decimal('0.0001'))
                })
        return result


# ============================================================================
# Owner's / Director's Loan (from owners_loan.xlsx or owners_loan.pdf)
# ============================================================================

# Data row in PDF: date (DD/MM/YYYY) + account (U\d+ or sort-code) + amount
_OWNERS_LOAN_PDF_ROW = re.compile(
    r"^(\d{1,2}/\d{1,2}/\d{4})\s+(U\d+|\d{2}-\d{2}-\d{2}\s+\d+)\s+(-?[\d,]+\.?\d*)\s"
)


def _parse_owners_loan_pdf(path: Path) -> tuple[list[tuple[date, str, Decimal]], list[tuple[date, str, Decimal]]]:
    """
    Extract (date, account, amount) rows from owners_loan.pdf. Uses pdfplumber.
    Returns (in_rows, out_rows). If the PDF has standalone totals -514,005.62 and 513,275.13,
    splits by blocks (Director -> Business vs Business -> Director). Otherwise uses sign:
    negative = in, positive = out (single list with signed amounts, caller splits).
    """
    try:
        import pdfplumber
    except ImportError:
        raise RuntimeError("PDF support requires pdfplumber; pip install pdfplumber")
    with pdfplumber.open(path) as pdf:
        full_text = ""
        for p in pdf.pages:
            t = p.extract_text()
            if t:
                full_text += t + "\n"
    lines = [ln.strip() for ln in full_text.splitlines() if ln.strip()]
    in_rows: list[tuple[date, str, Decimal]] = []
    out_rows: list[tuple[date, str, Decimal]] = []
    seen: set[tuple[str, str, str]] = set()

    def parse_row(line: str) -> tuple[date, str, Decimal] | None:
        m = _OWNERS_LOAN_PDF_ROW.match(line)
        if not m:
            return None
        day_s, account_s, amount_s = m.group(1), m.group(2).strip().upper(), m.group(3).replace(",", "")
        try:
            dt = datetime.strptime(day_s, "%d/%m/%Y").date()
            amt = Decimal(amount_s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (ValueError, Exception):
            return None
        return (dt, account_s, amt)

    def _norm(dt: date, account_s: str, amt: Decimal) -> tuple:
        return (str(dt), account_s, str(amt.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)))

    def add_in(dt: date, account_s: str, amt: Decimal) -> None:
        key = _norm(dt, account_s, amt)
        if key in seen:
            return
        seen.add(key)
        in_rows.append((dt, account_s, amt))

    def add_out(dt: date, account_s: str, amt: Decimal) -> None:
        key = _norm(dt, account_s, amt)
        if key in seen:
            return
        seen.add(key)
        out_rows.append((dt, account_s, amt))

    # Look for block-delimiting totals (normalize: no commas)
    idx_first_total = -1  # line that is -514,005.62
    idx_second_total = -1  # line that is 513,275.13
    for i, line in enumerate(lines):
        clean = line.replace(",", "").strip()
        if re.match(r"^-?\d+\.?\d*$", clean):
            try:
                v = Decimal(clean)
                if v < 0 and idx_first_total < 0:
                    idx_first_total = i
                elif v > 0 and idx_first_total >= 0 and idx_second_total < 0:
                    idx_second_total = i
                    break
            except Exception:
                pass

    if idx_first_total >= 0 and idx_second_total >= 0:
        # Block-based: rows before first total = Director -> Business; between totals = Business -> Director
        for i in range(idx_first_total):
            row = parse_row(lines[i])
            if row and row[2] != 0:
                dt, account_s, amt = row
                if amt < 0 and account_s != "U6361921":
                    add_in(dt, account_s, abs(amt))
        for i in range(idx_first_total + 1, idx_second_total):
            row = parse_row(lines[i])
            if row and row[2] != 0:
                dt, account_s, amt = row
                if amt > 0:
                    add_out(dt, account_s, amt)
    else:
        # Fallback: sign-based for all lines
        for line in lines:
            if line.startswith("Date") or line in ("Barclays", "Wise", "IBKR to IBKR") or line.startswith("-- ") or "Summary:" in line:
                continue
            clean = line.replace(",", "")
            if _OWNERS_LOAN_PDF_ROW.match(line) is None and re.match(r"^-?\d+\.?\d*$", clean):
                continue
            row = parse_row(line)
            if not row or row[2] == 0:
                continue
            dt, account_s, amt = row
            if amt < 0:
                if account_s != "U6361921":
                    add_in(dt, account_s, abs(amt))
            else:
                add_out(dt, account_s, amt)
    return (in_rows, out_rows)


def _apply_owners_loan_from_pdf(generator: TrialBalanceGenerator, path: Path, period_end: date) -> None:
    """Post owner's loan from PDF using parsed in/out rows."""
    in_rows, out_rows = _parse_owners_loan_pdf(path)
    for dt, account_s, amt_abs in in_rows:
        if dt > period_end:
            continue
        generator._debit("1103", amt_abs, f"Owner's loan in ({account_s})")
        generator._credit("2101", amt_abs, f"Owner's loan in ({account_s})")
    for dt, account_s, amt_abs in out_rows:
        if dt > period_end:
            continue
        generator._debit("2101", amt_abs, f"Owner's loan out ({account_s})")
        generator._credit("1103", amt_abs, f"Owner's loan out ({account_s})")


def apply_owners_loan(generator: TrialBalanceGenerator, path: Path, period_end: date) -> None:
    """
    Load owner's loan movements from Excel or PDF and post to 1103 (Cash at Bank - Other)
    and 2101 (Director's / Owner's Loan).

    - If path is .pdf: parses PDF text (no formulas). Negative = Director -> Business (skip U6361921),
      positive = Business -> Director. Requires pdfplumber.
    - If path is .xlsx: expects sheet 'owners loan' with Date, Account, Amount. Supports
      "Summary: Director -> Business" / "Summary: Business -> Director" sections; else sign convention.
    """
    if not path.exists():
        return
    if path.suffix.lower() == ".pdf":
        _apply_owners_loan_from_pdf(generator, path, period_end)
        return
    if pd is None:
        raise RuntimeError("pandas required for --owners-loan (Excel); pip install pandas openpyxl")
    try:
        df = pd.read_excel(path, sheet_name='owners loan', header=0)
    except Exception as e:
        raise RuntimeError(f"Failed to read owners_loan.xlsx sheet 'owners loan': {e}") from e
    # Column names (first row)
    cols = {str(c).strip().lower(): c for c in df.columns}
    date_col = cols.get('date') or cols.get('date/time') or df.columns[0]
    account_col = cols.get('account') or df.columns[1] if len(df.columns) > 1 else None
    amount_col = cols.get('amount') or df.columns[2] if len(df.columns) > 2 else None
    if account_col is None or amount_col is None:
        raise ValueError("owners_loan.xlsx must have Date, Account, Amount columns")
    col0 = df.columns[0]
    current_section: str | None = None  # 'in' = Director -> Business, 'out' = Business -> Director
    for _, row in df.iterrows():
        # Detect section headers (in first column)
        cell0 = row.get(col0, None)
        if pd.notna(cell0) and isinstance(cell0, str):
            s = str(cell0).strip()
            if "Director" in s and "->" in s and "Business" in s and s.find("Director") < s.find("Business"):
                current_section = "in"   # Director -> Business (money in)
                continue
            if "Business" in s and "->" in s and "Director" in s and s.find("Business") < s.find("Director"):
                current_section = "out"  # Business -> Director (money out)
                continue
        if current_section is None:
            continue
        # Data row: need valid date and amount
        raw_date = row.get(date_col, None)
        raw_account = row.get(account_col, None)
        raw_amt = row.get(amount_col, None)
        if pd.isna(raw_date) or pd.isna(raw_amt):
            continue
        try:
            dt = pd.to_datetime(raw_date, errors='coerce')
            if pd.isna(dt) or dt.date() > period_end:
                continue
        except Exception:
            continue
        try:
            amt = Decimal(str(raw_amt).replace(",", "")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except Exception:
            continue
        if amt == 0:
            continue
        acct_str = str(raw_account).strip().upper() if pd.notna(raw_account) else ""
        # Director -> Business: company receives (skip U6361921 – in Flex)
        if current_section == "in":
            if acct_str == "U6361921":
                continue
            amt_abs = abs(amt)
            memo = f"Owner's loan in ({raw_account})"
            generator._debit("1103", amt_abs, memo)
            generator._credit("2101", amt_abs, memo)
        # Business -> Director: company pays
        else:
            amt_abs = abs(amt)
            memo = f"Owner's loan out ({raw_account})"
            generator._debit("2101", amt_abs, memo)
            generator._credit("1103", amt_abs, memo)


# ============================================================================
# HTML Report Generator
# ============================================================================

def _render_tax_sections(tax_comp: Any, generator: TrialBalanceGenerator) -> str:
    """Render tax computation, CT liability, Section 104 schedule, CT600, variance."""
    out: list[str] = []
    
    # Tax Computation Schedule
    tp = tax_comp.taxable_profit or Decimal('0')
    ct = tax_comp.corporation_tax or Decimal('0')
    rate_pct = (ct / tp * 100).quantize(Decimal('0.01')) if tp and tp > 0 else Decimal('0')
    div_exempt = tax_comp.calculate_dividend_exemption()
    gains = tax_comp.calculate_capital_gains()
    mgmt_ibkr, mgmt_other = tax_comp.calculate_management_expenses()
    ir = tax_comp.interest_relief_result
    allow_int = ir.allowable_interest if ir else Decimal('0')
    int_inc = generator.accounts.get('4100')
    int_inc_cr = int_inc.credit if int_inc else Decimal('0')
    non_trading = (int_inc_cr - mgmt_ibkr - mgmt_other - allow_int).quantize(Decimal('0.01'))
    
    out.append("""
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">Tax Computation Schedule</div>
            <table>
                <thead><tr><th>Description</th><th class="number">Amount (£)</th></tr></thead>
                <tbody>""")
    out.append(f"""<tr><td>Dividend income (exempt)</td><td class="number">{div_exempt:,.2f}</td></tr>""")
    out.append(f"""<tr><td>Interest received (taxable)</td><td class="number">{int_inc_cr:,.2f}</td></tr>""")
    out.append(f"""<tr><td>Less: Management expenses (IBKR)</td><td class="number">({mgmt_ibkr:,.2f})</td></tr>""")
    out.append(f"""<tr><td>Less: Management expenses (other)</td><td class="number">({mgmt_other:,.2f})</td></tr>""")
    out.append(f"""<tr><td>Less: Interest paid (allowable)</td><td class="number">({allow_int:,.2f})</td></tr>""")
    out.append(f"""<tr><td><strong>Taxable non-trading profit</strong></td><td class="number"><strong>{non_trading:,.2f}</strong></td></tr>""")
    out.append(f"""<tr><td>Capital gains (Section 104)</td><td class="number">{gains:,.2f}</td></tr>""")
    out.append(f"""<tr class="total-row"><td><strong>Total taxable profit (CT600)</strong></td><td class="number"><strong>{tp:,.2f}</strong></td></tr>""")
    out.append("</tbody></table></div>")
    
    # Interest Relief Schedule (if interest paid)
    if ir and ir.total_interest_paid > 0:
        out.append("""
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">Interest Relief (ICR)</div>
            <table>
                <thead><tr><th>Description</th><th class="number">Amount (£)</th></tr></thead>
                <tbody>""")
        out.append(f"""<tr><td>Interest paid</td><td class="number">{ir.total_interest_paid:,.2f}</td></tr>""")
        out.append(f"""<tr><td>Taxable earnings (proxy)</td><td class="number">{ir.taxable_earnings:,.2f}</td></tr>""")
        out.append(f"""<tr><td>ICR limit (30%)</td><td class="number">{ir.icr_limit:,.2f}</td></tr>""")
        out.append(f"""<tr><td>Allowable interest</td><td class="number">{ir.allowable_interest:,.2f}</td></tr>""")
        out.append(f"""<tr><td>Disallowed (carry forward)</td><td class="number">{ir.disallowed_interest:,.2f}</td></tr>""")
        if ir.warning:
            out.append(f'<tr><td colspan="2" class="meta">{ir.warning}</td></tr>')
        out.append("</tbody></table></div>")
    
    # Corporation Tax Liability
    out.append("""
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">Corporation Tax Liability</div>
            <table>
                <thead><tr><th>Description</th><th class="number">Amount (£)</th></tr></thead>
                <tbody>""")
    out.append(f"""<tr><td>Taxable profit</td><td class="number">{tp:,.2f}</td></tr>""")
    out.append(f"""<tr><td>Effective rate</td><td class="number">{rate_pct:.2f}%</td></tr>""")
    out.append(f"""<tr class="total-row"><td><strong>Corporation Tax due</strong></td><td class="number"><strong>{ct:,.2f}</strong></td></tr>""")
    out.append("</tbody></table><div class='meta'>Payment due 9 months after period end.</div></div>")
    
    # Tax Shield Summary
    div_tax_saved = (div_exempt * (rate_pct / 100)).quantize(Decimal('0.01')) if rate_pct else Decimal('0')
    out.append("""
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">Tax Shield Summary</div>
            <table>
                <thead><tr><th>Relief</th><th>Status</th><th class="number">Amount / Tax saved (£)</th></tr></thead>
                <tbody>""")
    out.append(f"""<tr><td>Dividend exemption</td><td>✓ Applied</td><td class="number">{div_exempt:,.2f} (tax saved {div_tax_saved:,.2f})</td></tr>""")
    out.append("""<tr><td>SSE (Substantial Shareholding)</td><td>✗ Not applicable</td><td class="number">—</td></tr>""")
    out.append(f"""<tr><td>Management expense relief</td><td>✓ Applied</td><td class="number">{mgmt_ibkr + mgmt_other:,.2f}</td></tr>""")
    if ir and ir.total_interest_paid > 0:
        out.append(f"""<tr><td>Interest relief (ICR)</td><td>⚠ Partial</td><td class="number">Allowable {ir.allowable_interest:,.2f}</td></tr>""")
    out.append("</tbody></table></div>")
    
    # Section 104 Pooling Schedule (disposals)
    disposals = tax_comp.get_disposal_summary()
    if disposals:
        out.append("""
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">Section 104 Disposals (Tax)</div>
            <table>
                <thead>
                    <tr><th>Date</th><th>Symbol</th><th class="number">Qty</th><th class="number">Proceeds (£)</th><th class="number">Cost (£)</th><th class="number">Gain/(Loss) (£)</th><th>Rule</th></tr>
                </thead>
                <tbody>""")
        for d in disposals[:100]:  # cap for readability
            out.append(f"""<tr>
                <td>{d.date}</td><td>{d.symbol}</td><td class="number">{d.quantity:,.4f}</td>
                <td class="number">{d.proceeds_gbp:,.2f}</td><td class="number">{d.cost_gbp:,.2f}</td>
                <td class="number">{d.gain_loss_gbp:,.2f}</td><td>{d.matching_rule}</td>
            </tr>""")
        if len(disposals) > 100:
            out.append(f'<tr><td colspan="7" class="meta">… and {len(disposals) - 100} more disposals</td></tr>')
        net_g = tax_comp.calculate_capital_gains()
        out.append(f"""<tr class="total-row"><td colspan="5"><strong>Net capital gains</strong></td><td class="number"><strong>{net_g:,.2f}</strong></td><td></td></tr>""")
        out.append("</tbody></table></div>")
    
    # CT600 Box Mapping
    ct6 = tax_comp.ct600_mapping
    if ct6:
        out.append("""
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">CT600 Box Mapping</div>
            <table>
                <thead><tr><th>Box</th><th>Description</th><th class="number">Amount (£)</th></tr></thead>
                <tbody>""")
        out.append(f"""<tr><td>13</td><td>Non-trading profits</td><td class="number">{ct6.box_13_non_trading_profits:,.2f}</td></tr>""")
        out.append(f"""<tr><td>16</td><td>Chargeable gains</td><td class="number">{ct6.box_16_chargeable_gains:,.2f}</td></tr>""")
        out.append(f"""<tr><td>46</td><td>Taxable total profit</td><td class="number">{ct6.box_46_taxable_total_profit:,.2f}</td></tr>""")
        out.append(f"""<tr class="total-row"><td>500</td><td>Corporation Tax</td><td class="number"><strong>{ct6.box_500_corporation_tax:,.2f}</strong></td></tr>""")
        out.append("</tbody></table></div>")
    
    # Variance: FIFO vs Section 104 (trial balance gains vs tax gains)
    tb_gains = generator.accounts.get('4200')
    tb_losses = generator.accounts.get('5400')
    fifo_net = (tb_gains.credit - tb_gains.debit) - (tb_losses.debit - tb_losses.credit) if tb_gains and tb_losses else Decimal('0')
    s104_net = tax_comp.calculate_capital_gains()
    var = fifo_net - s104_net
    out.append("""
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">Variance: FIFO (Accounts) vs Section 104 (Tax)</div>
            <table>
                <thead><tr><th>Measure</th><th class="number">Amount (£)</th></tr></thead>
                <tbody>""")
    out.append(f"""<tr><td>FIFO net gain (trial balance 4200/5400)</td><td class="number">{fifo_net:,.2f}</td></tr>""")
    out.append(f"""<tr><td>Section 104 net gain (tax)</td><td class="number">{s104_net:,.2f}</td></tr>""")
    out.append(f"""<tr><td>Variance</td><td class="number">{var:,.2f}</td></tr>""")
    out.append("</tbody></table><div class='meta'>Difference due to same-day/30-day matching and average cost (Section 104) vs FIFO.</div></div>")

    return "\n".join(out)


def _render_qbo_reconciliation(rec: dict[str, Any]) -> str:
    """Render QuickBooks reconciliation section (bank + expense alignment)."""
    out: list[str] = []
    out.append("""
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">QuickBooks Reconciliation</div>
            <table>
                <thead><tr><th>Description</th><th class="number">Amount (£)</th></tr></thead>
                <tbody>""")
    out.append(f"""<tr><td>Book cash (1100+1101+1102+1103)</td><td class="number">{rec['book_cash']:,.2f}</td></tr>""")
    out.append(f"""<tr><td>QBO bank (end Balance)</td><td class="number">{rec['qbo_bal']:,.2f}</td></tr>""")
    out.append(f"""<tr><td>Difference (bank)</td><td class="number">{rec['diff_bank']:,.2f}</td></tr>""")
    out.append(f"""<tr><td>{'✓ Bank reconciled' if rec['reconciled_bank'] else '⚠ Unreconciled'}</td><td></td></tr>""")
    out.append("""<tr><td colspan="2" style="height: 0.5rem;"></td></tr>""")
    out.append(f"""<tr><td>Book expenses (5200+5300+5600)</td><td class="number">{rec['book_exp']:,.2f}</td></tr>""")
    out.append(f"""<tr><td>QBO outflows (sum |negative Amt|)</td><td class="number">{abs(rec['qbo_exp_sum']):,.2f}</td></tr>""")
    out.append(f"""<tr><td>Difference (expenses)</td><td class="number">{rec['diff_exp']:,.2f}</td></tr>""")
    out.append(f"""<tr><td>{'✓ Expenses aligned (within £1)' if rec['aligned_exp'] else '⚠ Variance'}</td><td></td></tr>""")
    out.append("</tbody></table>")
    out.append("<div class='meta'>Book figures from trial balance (IBKR). QBO from Transaction Detail by Account and Transaction List by Date (Cash basis, same period).</div>")
    out.append("</div>")
    return "\n".join(out)


def generate_html_report(
    generator: TrialBalanceGenerator,
    company_name: str,
    period_end: date,
    tax_comp: Optional[Any] = None,
    qbo_reconciliation: Optional[dict[str, Any]] = None,
) -> str:
    """Generate HTML trial balance report, optionally with tax and QuickBooks reconciliation sections."""
    
    tb = generator.get_trial_balance()
    holdings = generator.get_holdings_summary()
    
    total_debits = sum(row['debit'] for row in tb)
    total_credits = sum(row['credit'] for row in tb)
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trial Balance - {company_name}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ 
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #f5f5f5;
            padding: 2rem;
            color: #333;
        }}
        .container {{ max-width: 900px; margin: 0 auto; }}
        .header {{
            background: linear-gradient(135deg, #1a365d 0%, #2c5282 100%);
            color: white;
            padding: 2rem;
            border-radius: 8px 8px 0 0;
        }}
        .header h1 {{ font-size: 1.5rem; font-weight: 600; }}
        .header .subtitle {{ opacity: 0.9; margin-top: 0.5rem; }}
        .header .period {{ 
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255,255,255,0.2);
            font-size: 0.9rem;
        }}
        .card {{
            background: white;
            border-radius: 0 0 8px 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            margin-bottom: 2rem;
        }}
        .section-title {{
            background: #edf2f7;
            padding: 1rem 1.5rem;
            font-weight: 600;
            border-bottom: 1px solid #e2e8f0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 0.75rem 1.5rem;
            text-align: left;
        }}
        th {{
            background: #f7fafc;
            font-weight: 600;
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: #4a5568;
        }}
        td {{ border-bottom: 1px solid #edf2f7; }}
        tr:last-child td {{ border-bottom: none; }}
        .number {{ text-align: right; font-variant-numeric: tabular-nums; }}
        .total-row {{ 
            font-weight: 600;
            background: #f7fafc;
        }}
        .total-row td {{ border-top: 2px solid #2c5282; }}
        .balance-check {{
            padding: 1rem 1.5rem;
            background: #f0fff4;
            border-top: 1px solid #9ae6b4;
            color: #276749;
            font-weight: 500;
        }}
        .balance-check.error {{
            background: #fff5f5;
            border-top-color: #feb2b2;
            color: #c53030;
        }}
        .meta {{
            font-size: 0.8rem;
            color: #718096;
            padding: 1rem 1.5rem;
            border-top: 1px solid #edf2f7;
        }}
        .category {{ 
            padding-left: 2rem; 
            color: #4a5568;
        }}
        .category-header {{
            background: #fafafa;
            font-weight: 600;
            color: #2d3748;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{company_name}</h1>
            <div class="subtitle">Trial Balance</div>
            <div class="period">
                Period ending: {period_end.strftime('%d %B %Y')}<br>
                Prepared: {datetime.now().strftime('%d %B %Y at %H:%M')}
            </div>
        </div>
        
        <div class="card">
            <div class="section-title">Trial Balance</div>
            <table>
                <thead>
                    <tr>
                        <th>Code</th>
                        <th>Account</th>
                        <th class="number">Debit (£)</th>
                        <th class="number">Credit (£)</th>
                    </tr>
                </thead>
                <tbody>
"""
    
    # Group accounts by category
    categories = [
        ('Assets', ['1100', '1101', '1102', '1103', '1200']),
        ('Liabilities', ['2100', '2101']),
        ('Capital & Reserves', ['3000', '3100', '3200']),
        ('Income', ['4000', '4100', '4200', '4300']),
        ('Expenses', ['5000', '5100', '5200', '5300', '5400', '5500', '5600']),
    ]
    
    for cat_name, codes in categories:
        cat_rows = [r for r in tb if r['code'] in codes]
        if cat_rows:
            html += f'<tr class="category-header"><td colspan="4">{cat_name}</td></tr>\n'
            for row in cat_rows:
                html += f"""<tr>
                    <td class="category">{row['code']}</td>
                    <td>{row['name']}</td>
                    <td class="number">{row['debit']:,.2f}</td>
                    <td class="number">{row['credit']:,.2f}</td>
                </tr>\n"""
    
    balance_ok = abs(total_debits - total_credits) < Decimal('0.01')
    
    html += f"""
                    <tr class="total-row">
                        <td></td>
                        <td><strong>TOTAL</strong></td>
                        <td class="number"><strong>{total_debits:,.2f}</strong></td>
                        <td class="number"><strong>{total_credits:,.2f}</strong></td>
                    </tr>
                </tbody>
            </table>
            <div class="balance-check {'error' if not balance_ok else ''}">
                {'✓ Trial balance balanced' if balance_ok else f'⚠ Out of balance by £{abs(total_debits - total_credits):,.2f}'}
            </div>
        </div>
"""
    
    # Tax computation sections (if tax_comp provided)
    if tax_comp is not None:
        html += _render_tax_sections(tax_comp, generator)

    # QuickBooks reconciliation (if qbo_reconciliation data provided)
    if qbo_reconciliation is not None:
        html += _render_qbo_reconciliation(qbo_reconciliation)

    # Holdings schedule
    if holdings:
        html += """
        <div class="card" style="border-radius: 8px;">
            <div class="section-title">Schedule: Listed Investments at Cost</div>
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th class="number">Quantity</th>
                        <th class="number">Cost (£)</th>
                        <th class="number">Avg Cost/Share (£)</th>
                    </tr>
                </thead>
                <tbody>
"""
        total_holdings = Decimal('0')
        for h in holdings:
            total_holdings += h['cost_gbp']
            html += f"""<tr>
                <td>{h['symbol']}</td>
                <td class="number">{h['quantity']:,.4f}</td>
                <td class="number">{h['cost_gbp']:,.2f}</td>
                <td class="number">{h['avg_cost']:,.4f}</td>
            </tr>\n"""
        
        html += f"""
                    <tr class="total-row">
                        <td colspan="2"><strong>TOTAL</strong></td>
                        <td class="number"><strong>{total_holdings:,.2f}</strong></td>
                        <td></td>
                    </tr>
                </tbody>
            </table>
        </div>
"""
    
    meta = "Generated using HMRC monthly exchange rates • FRS 105 historical cost basis • FIFO cost method (financial statements)"
    if tax_comp is not None:
        meta += " • Section 104 pooling (tax computation)"
    if qbo_reconciliation is not None:
        meta += " • QuickBooks reconciliation"
    html += f"""
        <div class="meta">
            {meta}
        </div>
    </div>
</body>
</html>
"""
    return html


# ============================================================================
# Main
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Generate UK trial balance from IBKR Flex Query export'
    )
    parser.add_argument('flex_query', type=Path, help='Path to IBKR Flex Query CSV file')
    parser.add_argument('--period-end', required=True, help='Period end date (YYYY-MM-DD)')
    parser.add_argument('--company', default='Investment Holding Company', help='Company name')
    parser.add_argument('--output', type=Path, help='Output HTML file path')
    parser.add_argument('--management-expenses', type=Path, help='CSV of management/deductible expenses to include in tax computation (description, amount_gbp, date). Include all allowable expenses not in the Flex data.')
    parser.add_argument('--owners-loan', type=Path, default=None, help="Excel (owners_loan.xlsx) or PDF (owners_loan.pdf) with director's loan movements. Company bank rows post to 1103/2101; U6361921 excluded (in Flex). Use PDF if the spreadsheet uses references/formulas.")
    parser.add_argument('--qbo-accounts', type=Path, default=None, help='QBO Transaction Detail by Account (bank) – include to embed QuickBooks reconciliation in the report')
    parser.add_argument('--qbo-date', type=Path, default=None, help='QBO Transaction List by Date (expenses) – include to embed QuickBooks reconciliation in the report')

    args = parser.parse_args()
    
    if not args.flex_query.exists():
        print(f"Error: File not found: {args.flex_query}", file=sys.stderr)
        sys.exit(1)
    
    try:
        period_end = datetime.strptime(args.period_end, '%Y-%m-%d').date()
    except ValueError:
        print(f"Error: Invalid date format. Use YYYY-MM-DD", file=sys.stderr)
        sys.exit(1)
    
    print(f"Processing {args.flex_query}...")
    
    # Initialize
    rate_cache = HMRCRateCache()
    
    # Parse Flex Query
    flex_parser = FlexQueryParser(args.flex_query, rate_cache)
    # Report trade counts by asset class
    from collections import Counter
    class_counts = Counter(t.asset_class for t in flex_parser.trades)
    print(f"  Found {len(flex_parser.trades)} trades: "
          + ", ".join(f"{cls} {n}" for cls, n in sorted(class_counts.items())))
    print(f"  Found {len(flex_parser.cash_transactions)} cash transactions")
    print(f"  Found {len(flex_parser.positions)} positions")
    
    # Generate trial balance
    generator = TrialBalanceGenerator(flex_parser, rate_cache, period_end)
    generator.process()
    # Owner's / director's loan (Barclays etc.) from Excel
    if args.owners_loan and args.owners_loan.exists():
        apply_owners_loan(generator, args.owners_loan, period_end)
        print(f"  Applied owner's loan from {args.owners_loan}")
    
    # Tax computation (Section 104 + CT) if modules available
    tax_comp = None
    if TaxComputation and generator.section_104:
        tax_comp = TaxComputation(
            generator,
            generator.section_104,
            management_expenses_path=args.management_expenses,
        )
        tax_comp.calculate_taxable_profit()
        tax_comp.calculate_corporation_tax()
        tax_comp.generate_ct600_mapping()
    
    # QuickBooks reconciliation data (if QBO exports provided)
    qbo_rec = None
    if (args.qbo_accounts or args.qbo_date) and get_reconciliation_data:
        book_cash = Decimal('0')
        book_exp = Decimal('0')
        for code in ('1100', '1101', '1102', '1103'):
            acc = generator.accounts.get(code)
            if acc:
                book_cash += acc.debit - acc.credit
        for code in ('5200', '5300', '5600'):
            acc = generator.accounts.get(code)
            if acc:
                book_exp += acc.debit - acc.credit
        qbo_rec = get_reconciliation_data(book_cash, book_exp, args.qbo_accounts, args.qbo_date)

    # Generate HTML report
    html = generate_html_report(generator, args.company, period_end, tax_comp=tax_comp, qbo_reconciliation=qbo_rec)
    
    # Output
    output_path = args.output or Path(f"trial_balance_{period_end.isoformat()}.html")
    output_path.write_text(html, encoding='utf-8')
    print(f"  Report written to: {output_path}")
    
    # Print summary
    tb = generator.get_trial_balance()
    print("\nTrial Balance Summary:")
    print("-" * 60)
    for row in tb:
        if row['debit'] > 0:
            print(f"  {row['code']} {row['name']:<35} DR £{row['debit']:>12,.2f}")
        if row['credit'] > 0:
            print(f"  {row['code']} {row['name']:<35} CR £{row['credit']:>12,.2f}")


if __name__ == '__main__':
    main()
