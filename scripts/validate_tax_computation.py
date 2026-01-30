#!/usr/bin/env python3
"""
Validate tax computation: Section 104, taxable profit, CT liability, CT600 mapping.

Run from repo root with same inputs as trial balance. Checks:
- Section 104 net capital gains matches disposal summary total
- Dividend exemption equals trial balance account 4000
- Taxable profit = non-trading + capital gains
- Corporation Tax calculated (19%/25%/marginal)
- CT600 box 46 = taxable profit, box 500 = CT
"""

import sys
from decimal import Decimal
from pathlib import Path

# Scripts dir for imports (ibkr_trial_balance, tax_computation)
_SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = _SCRIPTS.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from tax_computation import TaxComputation


def run_pipeline(flex_csv: Path, period_end_str: str, management_expenses_path: Path | None = None):
    """Load data, run trial balance + Section 104 + tax computation. Return (generator, tax_comp)."""
    from datetime import datetime
    from ibkr_trial_balance import (
        FlexQueryParser,
        HMRCRateCache,
        TrialBalanceGenerator,
    )
    period_end = datetime.strptime(period_end_str, "%Y-%m-%d").date()
    rate_cache = HMRCRateCache()
    parser = FlexQueryParser(flex_csv, rate_cache)
    generator = TrialBalanceGenerator(parser, rate_cache, period_end)
    generator.process()
    if not generator.section_104:
        return generator, None
    tax_comp = TaxComputation(generator, generator.section_104, management_expenses_path)
    tax_comp.calculate_taxable_profit()
    tax_comp.calculate_corporation_tax()
    tax_comp.generate_ct600_mapping()
    return generator, tax_comp


def validate(generator, tax_comp) -> list[tuple[str, bool, str]]:
    """Run validation checks. Return list of (check_name, passed, message)."""
    results = []
    if tax_comp is None:
        results.append(("Tax computation available", False, "Section 104 / TaxComputation not loaded"))
        return results

    # 1. Section 104 net gains = sum of disposal gain/loss
    disposals = tax_comp.get_disposal_summary()
    sum_gain_loss = sum(d.gain_loss_gbp for d in disposals)
    net_gains = tax_comp.calculate_capital_gains()
    ok = abs(sum_gain_loss - net_gains) < Decimal("0.02")
    results.append((
        "Section 104 disposals sum = net capital gains",
        ok,
        f"Sum {sum_gain_loss:.2f} vs net {net_gains:.2f}",
    ))

    # 2. Dividend exemption = account 4000 credit
    div_tb = generator.accounts.get("4000")
    div_tb_cr = div_tb.credit if div_tb else Decimal("0")
    div_exempt = tax_comp.calculate_dividend_exemption()
    ok = div_tb_cr == div_exempt
    results.append((
        "Dividend exemption = Account 4000",
        ok,
        f"4000 credit {div_tb_cr:.2f} vs exemption {div_exempt:.2f}",
    ))

    # 3. Taxable profit = non-trading + capital gains (sanity)
    tp = tax_comp.taxable_profit
    gains = tax_comp.calculate_capital_gains()
    int_cr = generator.accounts.get("4100").credit if generator.accounts.get("4100") else Decimal("0")
    mgmt_ibkr, mgmt_other = tax_comp.calculate_management_expenses()
    ir = tax_comp.interest_relief_result
    allow_int = ir.allowable_interest if ir else Decimal("0")
    non_trading = (int_cr - mgmt_ibkr - mgmt_other - allow_int).quantize(Decimal("0.01"))
    expected_tp = (non_trading + gains).quantize(Decimal("0.01"))
    ok = tp is not None and abs(tp - expected_tp) < Decimal("0.02")
    results.append((
        "Taxable profit = non-trading + capital gains",
        ok,
        f"TP {tp:.2f} vs expected {expected_tp:.2f}",
    ))

    # 4. Corporation Tax positive when profit positive
    ct = tax_comp.corporation_tax
    ok = (tp is not None and tp <= 0) or (ct is not None and ct >= 0)
    results.append((
        "Corporation Tax sign",
        ok,
        f"TP {tp}, CT {ct}",
    ))

    # 5. CT600 box 46 = taxable profit, box 500 = CT
    ct6 = tax_comp.ct600_mapping
    if ct6:
        ok46 = abs(ct6.box_46_taxable_total_profit - (tp or Decimal("0"))) < Decimal("0.02")
        ok500 = abs(ct6.box_500_corporation_tax - (ct or Decimal("0"))) < Decimal("0.02")
        results.append(("CT600 Box 46 = taxable profit", ok46, f"Box 46 {ct6.box_46_taxable_total_profit:.2f}"))
        results.append(("CT600 Box 500 = Corporation Tax", ok500, f"Box 500 {ct6.box_500_corporation_tax:.2f}"))
    else:
        results.append(("CT600 mapping", False, "No CT600 mapping"))

    return results


def main():
    flex = REPO_ROOT / "analysis" / "business.csv"
    if not flex.exists():
        print("Error: analysis/business.csv not found", file=sys.stderr)
        sys.exit(1)
    period_end = "2026-02-28"
    mgmt_path = REPO_ROOT / "analysis" / "management_expenses.csv"
    if not mgmt_path.exists():
        mgmt_path = None
    print("Running pipeline (trial balance + Section 104 + tax computation)...")
    generator, tax_comp = run_pipeline(flex, period_end, mgmt_path)
    print("Running validation checks...")
    results = validate(generator, tax_comp)
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, msg in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {msg}")
    print(f"\nResult: {passed}/{total} checks passed")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
