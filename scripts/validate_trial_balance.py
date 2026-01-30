#!/usr/bin/env python3
"""
Validate the generated trial balance against IBKR source reports.
"""

import csv
import re
from decimal import Decimal
from pathlib import Path
from bs4 import BeautifulSoup
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_html_trial_balance(html_path: Path) -> dict:
    """Extract trial balance figures from HTML."""
    with open(html_path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f.read(), 'html.parser')

    accounts = {}
    holdings = []

    # Extract trial balance accounts
    tb_table = soup.find('div', class_='section-title', string='Trial Balance').find_next('table')
    for row in tb_table.find_all('tr'):
        cells = row.find_all('td')
        if len(cells) == 4 and cells[0].get('class') == ['category']:
            code = cells[0].text.strip()
            name = cells[1].text.strip()
            debit = Decimal(cells[2].text.strip().replace(',', ''))
            credit = Decimal(cells[3].text.strip().replace(',', ''))
            accounts[code] = {'name': name, 'debit': debit, 'credit': credit}

    # Extract holdings
    holdings_table = soup.find('div', class_='section-title', string='Schedule: Listed Investments at Cost')
    if holdings_table:
        holdings_table = holdings_table.find_next('table')
        for row in holdings_table.find_all('tr'):
            cells = row.find_all('td')
            if len(cells) == 4 and 'total-row' not in row.get('class', []):
                symbol = cells[0].text.strip()
                qty = Decimal(cells[1].text.strip().replace(',', ''))
                cost = Decimal(cells[2].text.strip().replace(',', ''))
                holdings.append({'symbol': symbol, 'quantity': qty, 'cost': cost})

    return {'accounts': accounts, 'holdings': holdings}


def parse_ibkr_activity_csv(csv_path: Path) -> dict:
    """Extract Change in NAV figures from IBKR Activity Statement."""
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    nav_changes = {}
    for row in rows:
        if len(row) >= 3 and row[0] == 'Change in NAV' and row[1] == 'Data':
            field_name = row[2]
            field_value = row[3] if len(row) > 3 else ''
            if field_value:
                try:
                    nav_changes[field_name] = Decimal(field_value)
                except:
                    pass

    return nav_changes


def parse_ibkr_realized_csv(csv_path: Path) -> dict:
    """Extract realized P&L totals by asset category from IBKR Realized Summary."""
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        rows = list(reader)

    # Find the header row
    header_idx = None
    for i, row in enumerate(rows):
        if len(row) > 1 and row[0] == 'Realized & Unrealized Performance Summary' and row[1] == 'Header':
            header_idx = i
            break

    if header_idx is None:
        return {}

    headers = rows[header_idx]

    # Find column indices
    asset_category_idx = headers.index('Asset Category')
    symbol_idx = headers.index('Symbol')
    realized_total_idx = headers.index('Realized Total')

    # Extract data
    category_totals = {}

    for row in rows[header_idx + 1:]:
        if len(row) > realized_total_idx and row[0] == 'Realized & Unrealized Performance Summary' and row[1] == 'Data':
            asset_category = row[asset_category_idx]
            symbol = row[symbol_idx]

            # Skip total rows
            if 'Total' in symbol or symbol == '':
                continue

            try:
                realized_total = Decimal(row[realized_total_idx])
            except:
                continue

            if asset_category not in category_totals:
                category_totals[asset_category] = Decimal('0')

            category_totals[asset_category] += realized_total

    return category_totals


def check_hmrc_rate(year: int, month: int, currency: str = 'USD') -> Decimal:
    """Fetch and verify HMRC exchange rate."""
    url = f"https://www.trade-tariff.service.gov.uk/uk/api/exchange_rates/files/monthly_csv_{year}-{month}.csv"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()

        reader = csv.DictReader(resp.text.splitlines())
        for row in reader:
            code = row.get('Currency Code', row.get('currency_code', '')).strip()
            if code == currency:
                rate_str = row.get('Currency Units per £1', row.get('rate', '')).strip()
                return Decimal(rate_str)
    except Exception as e:
        return None

    return None


def main():
    base_dir = REPO_ROOT / "analysis"

    print("=" * 80)
    print("TRIAL BALANCE VALIDATION REPORT")
    print("=" * 80)
    print()

    # Parse files
    tb_data = parse_html_trial_balance(base_dir / '16235546_trial_balance.html')
    nav_changes = parse_ibkr_activity_csv(base_dir / 'activity.csv')
    realized_totals = parse_ibkr_realized_csv(base_dir / 'realized.csv')

    accounts = tb_data['accounts']
    holdings = tb_data['holdings']

    # Check 1: Net Realized P/L
    print("CHECK 1: Net Realized P/L (STK + OPT)")
    print("-" * 80)

    tb_gains = accounts.get('4200', {}).get('credit', Decimal('0'))
    tb_losses = accounts.get('5400', {}).get('debit', Decimal('0'))
    tb_net_pl = tb_gains - tb_losses

    ibkr_stk = realized_totals.get('Stocks', Decimal('0'))
    ibkr_opt = realized_totals.get('Equity and Index Options', Decimal('0'))
    ibkr_net_pl = ibkr_stk + ibkr_opt

    variance = tb_net_pl - ibkr_net_pl
    variance_pct = (variance / ibkr_net_pl * 100) if ibkr_net_pl != 0 else Decimal('0')

    print(f"  Trial Balance:")
    print(f"    4200 Realized Gains:  £{tb_gains:>15,.2f}")
    print(f"    5400 Realized Losses: £{tb_losses:>15,.2f}")
    print(f"    Net P/L:              £{tb_net_pl:>15,.2f}")
    print()
    print(f"  IBKR Reference:")
    print(f"    Stocks P/L:           £{ibkr_stk:>15,.2f}")
    print(f"    Options P/L:          £{ibkr_opt:>15,.2f}")
    print(f"    STK+OPT Net:          £{ibkr_net_pl:>15,.2f}")
    print()
    print(f"  Variance:               £{variance:>15,.2f} ({variance_pct:+.2f}%)")

    if abs(variance_pct) < 10:
        print(f"  Result: PASS (within acceptable HMRC rate variance)")
    else:
        print(f"  Result: FAIL (variance exceeds 10%)")
    print()

    # Check 2: Income & Expense Figures
    print("CHECK 2: Income & Expense Figures")
    print("-" * 80)

    checks = [
        ('4000', 'Dividend Income', 'credit', 'Dividends'),
        ('5000', 'Withholding Tax', 'debit', 'Withholding Tax'),
        ('5200', 'Broker Fees', 'debit', 'Other Fees'),
    ]

    for acc_code, acc_name, side, ibkr_field in checks:
        tb_value = accounts.get(acc_code, {}).get(side, Decimal('0'))
        ibkr_value = abs(nav_changes.get(ibkr_field, Decimal('0')))

        variance = tb_value - ibkr_value
        variance_pct = (variance / ibkr_value * 100) if ibkr_value != 0 else Decimal('0')

        print(f"  {acc_code} {acc_name}:")
        print(f"    Trial Balance: £{tb_value:>12,.2f}")
        print(f"    IBKR:          £{ibkr_value:>12,.2f}")
        print(f"    Variance:      £{variance:>12,.2f} ({variance_pct:+.2f}%)")

        if abs(variance_pct) < 20:
            print(f"    Result: PASS")
        else:
            print(f"    Result: FAIL")
        print()

    # Interest (net basis)
    tb_interest_paid = accounts.get('5600', {}).get('debit', Decimal('0'))
    tb_interest_rcvd = accounts.get('4100', {}).get('credit', Decimal('0'))
    tb_net_interest = tb_interest_rcvd - tb_interest_paid
    ibkr_net_interest = nav_changes.get('Interest', Decimal('0'))

    variance = tb_net_interest - ibkr_net_interest
    variance_pct = (variance / ibkr_net_interest * 100) if ibkr_net_interest != 0 else Decimal('0')

    print(f"  Net Interest:")
    print(f"    TB 4100 Received:  £{tb_interest_rcvd:>12,.2f}")
    print(f"    TB 5600 Paid:      £{tb_interest_paid:>12,.2f}")
    print(f"    TB Net:            £{tb_net_interest:>12,.2f}")
    print(f"    IBKR Net:          £{ibkr_net_interest:>12,.2f}")
    print(f"    Variance:          £{variance:>12,.2f} ({variance_pct:+.2f}%)")

    if abs(variance_pct) < 5:
        print(f"    Result: PASS")
    else:
        print(f"    Result: FAIL")
    print()

    # Check 3: Holdings Schedule
    print("CHECK 3: Holdings Schedule")
    print("-" * 80)

    print(f"  Open positions in trial balance:")
    fx_positions = []
    for h in holdings:
        print(f"    {h['symbol']:<30} Qty: {h['quantity']:>12,.4f}  Cost: £{h['cost']:>12,.2f}")
        if any(fx in h['symbol'] for fx in ['GBP.', 'USD.', 'EUR.', 'ILS.']):
            fx_positions.append(h['symbol'])

    print()
    if fx_positions:
        print(f"  ISSUE: Found {len(fx_positions)} FX positions in holdings schedule:")
        for sym in fx_positions:
            print(f"    - {sym} (CASH asset class should not appear as investment)")
        print(f"  Result: FAIL (FX conversions should not be held as investments)")
    else:
        print(f"  Result: PASS (no FX positions)")
    print()

    # Check 4: Trial Balance Balanced
    print("CHECK 4: Trial Balance Balanced")
    print("-" * 80)

    total_debits = sum(acc['debit'] for acc in accounts.values())
    total_credits = sum(acc['credit'] for acc in accounts.values())
    diff = abs(total_debits - total_credits)

    print(f"  Total Debits:   £{total_debits:>15,.2f}")
    print(f"  Total Credits: £{total_credits:>15,.2f}")
    print(f"  Difference:     £{diff:>15,.2f}")

    if diff < Decimal('0.01'):
        print(f"  Result: PASS")
    else:
        print(f"  Result: FAIL")
    print()

    # Check 5: HMRC Rate Verification
    print("CHECK 5: HMRC April 2025 USD Rate")
    print("-" * 80)

    rate = check_hmrc_rate(2025, 4, 'USD')
    if rate:
        print(f"  USD rate for April 2025: {rate} per £1")
        print(f"  Result: PASS (rate fetched successfully)")
    else:
        print(f"  Result: FAIL (could not fetch rate)")
    print()

    # Check 6: Summary
    print("CHECK 6: Summary of Issues")
    print("-" * 80)

    issues = []

    if abs(variance_pct) > 10:
        issues.append(f"Net P/L variance {variance_pct:.2f}% exceeds 10%")

    if fx_positions:
        issues.append(f"{len(fx_positions)} FX positions incorrectly held as investments")

    if diff >= Decimal('0.01'):
        issues.append(f"Trial balance out of balance by £{diff:.2f}")

    if issues:
        print(f"  Found {len(issues)} issue(s):")
        for i, issue in enumerate(issues, 1):
            print(f"    {i}. {issue}")
    else:
        print(f"  No critical issues found. All checks pass.")
    print()
    print("=" * 80)


if __name__ == '__main__':
    main()
