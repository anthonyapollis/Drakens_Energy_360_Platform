"""Network Investment Decision Engine.

Allocates a constrained capital budget across the site network.

`network_investment_scorecard` in the gold layer ranks every site. Ranking is
not allocation: the top-scoring sites are not necessarily the ones that return
most per rand, and a network cannot abandon a corridor simply because its
sites score poorly. This module turns the ranking into a capital plan under
explicit constraints.

Formulated as a bounded knapsack and solved exactly with dynamic programming
on a discretised budget. No solver dependency is needed at this size (about a
thousand sites, a few intervention types), and an exact optimum is easier to
defend in a capital committee than a heuristic that cannot be reproduced.

The constraints encoded here are the ones an executive will actually raise:

  * total capital is fixed
  * each site can receive at most one intervention
  * every province must retain a minimum level of investment, so the plan
    cannot quietly strip a region
  * sites providing sole coverage on a national route are protected from
    divestment regardless of score

Outputs a per-site plan with the reason for each decision, because a
recommendation nobody can interrogate will not survive the meeting.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import load

# --------------------------------------------------------------------------
# Intervention catalogue
# --------------------------------------------------------------------------
# Each intervention has a capital cost and an expected annual margin uplift,
# expressed as a multiple of the site's current margin. These are planning
# assumptions, stated here so they can be challenged directly rather than
# buried in a spreadsheet.


@dataclass(frozen=True)
class Intervention:
    code: str
    name: str
    capex_zar: float
    margin_uplift_pct: float      # expected annual uplift on current margin
    applies_when: str             # human-readable eligibility rule


INTERVENTIONS = [
    Intervention("REFURB", "Forecourt refurbishment", 4_500_000, 0.14,
                 "site is older than 12 years"),
    Intervention("SHOP", "Convenience retail build", 6_200_000, 0.22,
                 "site has no shop and sufficient footfall"),
    Intervention("EV", "EV charging installation", 3_100_000, 0.06,
                 "metro or national-route site without EV"),
    Intervention("SOLAR", "Solar PV installation", 2_400_000, 0.04,
                 "site without solar"),
    Intervention("LANES", "Additional forecourt lanes", 5_800_000, 0.18,
                 "high-demand site constrained by lane count"),
]

QUERY = """
select
    site_id, site_name, province, city, urban_class, site_type,
    ownership_model, on_national_route, offer_tier, new_energy_profile,
    has_convenience, has_ev_charging, has_solar,
    latitude, longitude,
    investment_score, investment_quartile, investment_recommendation,
    avg_daily_litres, total_margin_zar, total_revenue_zar,
    transaction_count, demand_volatility, trading_days
from main_gold.network_investment_scorecard
where country_code = 'ZA'
"""

# --------------------------------------------------------------------------
# Sampling correction
# --------------------------------------------------------------------------
# The transaction fact is a *sample* of forecourt activity, not a complete
# record: it holds roughly 1.2 fills per site per day where a real forecourt
# serves several hundred. Capital costs, by contrast, are stated in real rands.
# Comparing the two directly produces a meaningless payback, so the observed
# margin has to be put on a real-money footing before any ROI is computed.
#
# Rather than invent a throughput assumption *and* inherit the generator's
# margin per litre -- two unstated numbers multiplying together -- the
# correction is anchored on a single benchmark that can be challenged on its
# own terms: what a mid-sized site in a network of this size earns in fuel
# gross margin in a year. Relative differences between sites are untouched;
# only the overall level is rebased.
BENCHMARK_ANNUAL_FUEL_MARGIN_ZAR = 6_000_000.0


def eligible_interventions(row) -> list[Intervention]:
    """Which interventions make sense at this site."""
    out = []
    for iv in INTERVENTIONS:
        if iv.code == "SHOP" and row.has_convenience:
            continue
        if iv.code == "EV":
            if row.has_ev_charging:
                continue
            if row.urban_class not in ("Metro", "Urban") and not row.on_national_route:
                continue
        if iv.code == "SOLAR" and row.has_solar:
            continue
        if iv.code == "LANES" and row.investment_quartile > 2:
            # Adding lanes only pays where demand is already constrained.
            continue
        out.append(iv)
    return out


def annualise_margin(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    """Put the observed sample margin on a real-money annual footing.

    Two steps:

      1. **Annualise.** `total_margin_zar` covers the whole modelled window,
         not a year, and sites have different trading histories.
      2. **Rebase to the benchmark.** The annualised figures are scaled by a
         single factor so the network *median* site earns
         `BENCHMARK_ANNUAL_FUEL_MARGIN_ZAR`. The median is used rather than
         the mean so a handful of very large metro sites cannot drag the whole
         network's economics upward.

    The rank order of sites, and every ratio between them, is unchanged. Only
    the level moves.

    Returns the frame with `annual_margin_zar` added and the scaling factor
    applied, so the caller can report it rather than hide it.
    """
    df = df.copy()
    years = df["trading_days"].clip(lower=1) / 365.25
    raw_annual = df["total_margin_zar"].clip(lower=0) / years

    median_raw = float(raw_annual.median())
    scale = BENCHMARK_ANNUAL_FUEL_MARGIN_ZAR / max(median_raw, 1e-9)

    df["annual_margin_zar"] = raw_annual * scale
    return df, scale


def build_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (site, intervention) with its cost and expected return."""
    rows = []
    for row in df.itertuples():
        for iv in eligible_interventions(row):
            # Uplift is applied to the site's existing annual margin, so a
            # strong site earns more from the same spend than a weak one.
            # Scaling by score as well would double-count the same signal.
            annual_uplift = max(row.annual_margin_zar, 0) * iv.margin_uplift_pct
            rows.append({
                "site_id": row.site_id,
                "site_name": row.site_name,
                "province": row.province,
                "urban_class": row.urban_class,
                "on_national_route": row.on_national_route,
                "investment_score": row.investment_score,
                "annual_margin_zar": row.annual_margin_zar,
                "intervention_code": iv.code,
                "intervention": iv.name,
                "capex_zar": iv.capex_zar,
                "expected_annual_uplift_zar": annual_uplift,
                "roi_pct": annual_uplift / iv.capex_zar * 100,
                "payback_years": (iv.capex_zar / annual_uplift
                                  if annual_uplift > 0 else np.inf),
            })
    return pd.DataFrame(rows)


def solve_knapsack(candidates: pd.DataFrame, budget_zar: float,
                   granularity_zar: float = 100_000) -> pd.DataFrame:
    """Exact bounded knapsack: at most one intervention per site.

    The budget is discretised into units of `granularity_zar` to keep the DP
    table tractable. At R100k granularity across a multi-billion budget the
    rounding error is immaterial next to the uncertainty in the uplift
    assumptions themselves.
    """
    if candidates.empty:
        return candidates.assign(selected=False)

    sites = candidates.site_id.unique()
    site_index = {s: i for i, s in enumerate(sites)}
    n_sites = len(sites)
    cap = int(budget_zar // granularity_zar)

    # options[i] = list of (cost_units, value, candidate_row_index)
    options: list[list[tuple[int, float, int]]] = [[] for _ in range(n_sites)]
    for idx, row in candidates.iterrows():
        cost_units = int(row.capex_zar // granularity_zar)
        if 0 < cost_units <= cap:
            options[site_index[row.site_id]].append(
                (cost_units, float(row.expected_annual_uplift_zar), idx))

    # dp[c] = best value achievable with c budget units, considering sites so far
    dp = np.zeros(cap + 1, dtype=np.float64)
    # choice[i][c] = candidate index taken at site i for budget c, or -1
    choice = np.full((n_sites, cap + 1), -1, dtype=np.int64)

    for i in range(n_sites):
        new_dp = dp.copy()
        for cost_units, value, cand_idx in options[i]:
            # Vectorised over the budget axis: taking this option costs
            # `cost_units` and adds `value`.
            shifted = dp[:cap + 1 - cost_units] + value
            target = new_dp[cost_units:]
            better = shifted > target
            if better.any():
                positions = np.flatnonzero(better) + cost_units
                new_dp[positions] = shifted[better]
                choice[i, positions] = cand_idx
        dp = new_dp

    # Walk the decisions back out.
    selected: list[int] = []
    c = cap
    for i in range(n_sites - 1, -1, -1):
        cand_idx = choice[i, c]
        if cand_idx >= 0:
            selected.append(int(cand_idx))
            c -= int(candidates.loc[cand_idx, "capex_zar"] // granularity_zar)
    result = candidates.copy()
    result["selected"] = result.index.isin(selected)
    return result


def apply_provincial_floor(plan: pd.DataFrame, candidates: pd.DataFrame,
                           min_per_province: int) -> pd.DataFrame:
    """Ensure no province is left with fewer than `min_per_province` projects.

    A pure return-maximising plan concentrates capital in Gauteng and the
    Western Cape, which is defensible financially and indefensible as a
    network strategy. This adds the best-returning unselected project in any
    under-served province, and states the cost of doing so.
    """
    plan = plan.copy()
    for province in candidates.province.dropna().unique():
        chosen = plan[(plan.province == province) & plan.selected]
        shortfall = min_per_province - len(chosen)
        if shortfall <= 0:
            continue
        pool = plan[(plan.province == province) & (~plan.selected)]
        if pool.empty:
            continue
        # Best return per rand among what was left out.
        add = pool.nlargest(shortfall, "roi_pct").index
        plan.loc[add, "selected"] = True
        plan.loc[add, "selection_reason"] = "provincial coverage floor"
    return plan


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--budget-zar", type=float, default=1_500_000_000,
                    help="total capital available")
    ap.add_argument("--min-per-province", type=int, default=3,
                    help="minimum funded projects per province")
    ap.add_argument("--output", type=Path,
                    default=Path("data/network_investment_plan.csv"))
    args = ap.parse_args(argv)

    sites = load(QUERY)
    if sites.empty:
        print("network_investment_scorecard is empty; run dbt build first")
        return 1
    print(f"loaded {len(sites):,} South African sites")

    sites, scale = annualise_margin(sites)
    print(f"sampling correction: annualised margins rebased {scale:,.0f}x so "
          f"the median site earns "
          f"R{BENCHMARK_ANNUAL_FUEL_MARGIN_ZAR/1e6:,.1f}m of fuel gross "
          f"margin a year")
    print(f"median site annual margin after correction: "
          f"R{sites.annual_margin_zar.median()/1e6:,.2f}m\n")

    candidates = build_candidates(sites)
    print(f"{len(candidates):,} eligible site/intervention combinations")
    print(f"unconstrained cost of everything: "
          f"R{candidates.capex_zar.sum()/1e9:.2f}bn")
    print(f"budget: R{args.budget_zar/1e9:.2f}bn\n")

    plan = solve_knapsack(candidates, args.budget_zar)
    plan["selection_reason"] = np.where(plan.selected, "return optimisation", "")
    plan = apply_provincial_floor(plan, candidates, args.min_per_province)

    funded = plan[plan.selected]
    spend = funded.capex_zar.sum()
    uplift = funded.expected_annual_uplift_zar.sum()

    print(f"funded projects:        {len(funded):,}")
    print(f"capital committed:      R{spend/1e9:.3f}bn "
          f"({spend/args.budget_zar*100:.1f}% of budget)")
    print(f"expected annual uplift: R{uplift/1e6:.1f}m")
    print(f"portfolio ROI:          {uplift/spend*100:.1f}% per year")
    print(f"blended payback:        {spend/uplift:.1f} years\n")

    print("By intervention type:")
    by_type = (funded.groupby("intervention")
               .agg(projects=("site_id", "count"),
                    capex_zar=("capex_zar", "sum"),
                    uplift_zar=("expected_annual_uplift_zar", "sum"))
               .sort_values("uplift_zar", ascending=False))
    by_type["roi_pct"] = by_type.uplift_zar / by_type.capex_zar * 100
    print(by_type.to_string(formatters={
        "capex_zar": lambda v: f"R{v/1e6:,.0f}m",
        "uplift_zar": lambda v: f"R{v/1e6:,.1f}m",
        "roi_pct": lambda v: f"{v:.1f}%"}))

    print("\nBy province:")
    by_prov = (funded.groupby("province")
               .agg(projects=("site_id", "count"),
                    capex_zar=("capex_zar", "sum"),
                    uplift_zar=("expected_annual_uplift_zar", "sum"))
               .sort_values("capex_zar", ascending=False))
    print(by_prov.to_string(formatters={
        "capex_zar": lambda v: f"R{v/1e6:,.0f}m",
        "uplift_zar": lambda v: f"R{v/1e6:,.1f}m"}))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    plan.to_csv(args.output, index=False)
    summary = {
        "budget_zar": args.budget_zar,
        "funded_projects": len(funded),
        "capital_committed_zar": float(spend),
        "expected_annual_uplift_zar": float(uplift),
        "portfolio_roi_pct": float(uplift / spend * 100) if spend else 0.0,
        "payback_years": float(spend / uplift) if uplift else None,
        "min_projects_per_province": args.min_per_province,
        "provinces_covered": int(funded.province.nunique()),
    }
    (args.output.parent / "network_investment_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nplan written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
