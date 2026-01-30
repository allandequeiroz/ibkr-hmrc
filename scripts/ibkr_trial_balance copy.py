#!/usr/bin/env python3
"""
IBKR Flex Query to UK Trial Balance Reconciliation Tool
For FRS 105 micro-entity: Historical cost basis, GBP functional currency

Usage:
    python ibkr_trial_balance.py <flex_query.csv> --period-end YYYY-MM-DD

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
from typing import Optional
import requests

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
        '1200': 'Listed Investments at Cost',
        
        # Liabilities
        '2100': 'Accruals and Deferred Income',
        
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
        
        for tx in self.parser.cash_transactions:
            self._process_cash_transaction(tx)
    
    def _process_trade(self, trade: Trade):
        """Process a single trade under FRS 105 historical cost."""
        # FX conversions are cash movements between currency accounts, not investments.
        # Crypto trades are custodied by Paxos, not IBKR — excluded from this TB.
        if trade.asset_class in ('CASH', 'CRYPTO'):
            return

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
                cost_gbp=cost_gbp
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
                self._credit('4200', gain_loss, f"Gain on {trade.symbol}")
            elif gain_loss < 0:
                self._debit('5400', abs(gain_loss), f"Loss on {trade.symbol}")
    
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
                    cost_gbp=lot.cost_gbp - cost_consumed
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
        """Get summary of holdings at cost."""
        result = []
        for symbol, lots in sorted(self.holdings.items()):
            total_qty = sum(lot.quantity for lot in lots)
            total_cost = sum(lot.cost_gbp for lot in lots)
            if total_qty > 0:
                result.append({
                    'symbol': symbol,
                    'quantity': total_qty,
                    'cost_gbp': total_cost,
                    'avg_cost': (total_cost / total_qty).quantize(Decimal('0.0001'))
                })
        return result


# ============================================================================
# HTML Report Generator
# ============================================================================

def generate_html_report(
    generator: TrialBalanceGenerator,
    company_name: str,
    period_end: date
) -> str:
    """Generate HTML trial balance report."""
    
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
        ('Assets', ['1100', '1101', '1102', '1200']),
        ('Liabilities', ['2100']),
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
    
    html += """
        <div class="meta">
            Generated using HMRC monthly exchange rates • FRS 105 historical cost basis • FIFO cost method
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
    skipped = sum(n for cls, n in class_counts.items() if cls in ('CASH', 'CRYPTO'))
    if skipped:
        print(f"  Skipping {skipped} trades (CASH=FX conversions, CRYPTO=Paxos)")
    print(f"  Found {len(flex_parser.cash_transactions)} cash transactions")
    print(f"  Found {len(flex_parser.positions)} positions")
    
    # Generate trial balance
    generator = TrialBalanceGenerator(flex_parser, rate_cache, period_end)
    generator.process()
    
    # Generate HTML report
    html = generate_html_report(generator, args.company, period_end)
    
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
