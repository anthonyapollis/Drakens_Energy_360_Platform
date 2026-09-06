"""Finance, planning and executive facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fact
from . import _common as c
from .. import reference as ref


@fact("fact_finance_revenue_cost")
def finance_revenue_cost(rng, ctx, profile):
    bu_codes = np.array([b[0] for b in ref.BUSINESS_UNITS])

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        revenue = rng.lognormal(13.4, 1.15, n)
        cogs = revenue * rng.uniform(0.78, 0.94, n)
        opex = revenue * rng.uniform(0.03, 0.11, n)
        df = pd.DataFrame({
            "finance_id": c.seq_ids("FIN", offset, n),
            "period_date": ts,
            "date_key": c.date_key(ts),
            "business_unit_code": rng.choice(bu_codes, n),
            "site_id": rng.choice(ctx.site_ids, n),
            "cost_centre_code": rng.choice(
                ctx.cost_centre["cost_centre_code"].to_numpy(), n),
            "revenue_zar": revenue.round(2),
            "cogs_zar": cogs.round(2),
            "gross_profit_zar": (revenue - cogs).round(2),
            "opex_zar": opex.round(2),
            "ebitda_zar": (revenue - cogs - opex).round(2),
            "depreciation_zar": (revenue * rng.uniform(0.004, 0.02, n)).round(2),
            "gross_margin_pct": ((revenue - cogs) / revenue * 100).round(3),
            "currency_code": "ZAR",
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_general_ledger")
def general_ledger(rng, ctx, profile):
    gl = ctx.gl_account
    gl_class = gl.set_index("gl_account_code")["account_class"]
    # Double entry needs a plausible pair of accounts per journal: something
    # credited and something debited for the same amount.
    credit_codes = gl.loc[gl["account_class"] == "Revenue",
                          "gl_account_code"].to_numpy()
    debit_codes = gl.loc[gl["account_class"].isin(["COGS", "Opex", "Capex"]),
                         "gl_account_code"].to_numpy()

    def make_chunk(offset, n):
        # Journals are emitted as balanced pairs: one credit line and one
        # debit line of equal value sharing a journal_id. Posting lines
        # independently produces a ledger where debits do not equal credits,
        # which no finance function would accept and which the
        # GL_DEBITS_EQUAL_CREDITS control in obs_reconciliation_controls
        # correctly rejects.
        pairs = (n + 1) // 2
        ts_pair = c.uniform_timestamps(rng, pairs).dt.normalize()
        amount_pair = rng.lognormal(10.6, 1.6, pairs).round(2)
        journal_pair = c.seq_ids("JNL", offset // 2, pairs, 12)

        # Interleave so each pair's two legs sit next to each other.
        ts = pd.Series(np.repeat(ts_pair.to_numpy(), 2)[:n])
        amount = np.repeat(amount_pair, 2)[:n]
        journal = np.repeat(journal_pair, 2)[:n]
        # Even positions are the credit leg, odd positions the debit leg.
        is_credit = (np.arange(n) % 2) == 0
        if n % 2:
            # An odd chunk size would truncate the final debit leg and leave
            # the ledger out of balance by that one amount. Zero it instead.
            amount = amount.copy()
            amount[-1] = 0.0

        codes = np.where(
            is_credit,
            rng.choice(credit_codes, n),
            rng.choice(debit_codes, n),
        )
        classes = gl_class.loc[codes].to_numpy()

        df = pd.DataFrame({
            "journal_line_id": c.seq_ids("GL", offset, n),
            "posting_date": ts,
            "date_key": c.date_key(ts),
            "journal_id": journal,
            "gl_account_code": codes,
            "account_class": classes,
            "cost_centre_code": rng.choice(
                ctx.cost_centre["cost_centre_code"].to_numpy(), n),
            "profit_centre_code": np.array(
                [f"PC{x:03d}" for x in rng.integers(1, 21, n)]),
            "legal_entity_code": np.array(
                [f"LE{x:02d}" for x in rng.integers(1, 13, n)]),
            "debit_amount_zar": np.where(is_credit, 0.0, amount).round(2),
            "credit_amount_zar": np.where(is_credit, amount, 0.0).round(2),
            "signed_amount_zar": np.where(is_credit, -amount, amount).round(2),
            "currency_code": "ZAR",
            "document_type": rng.choice(
                ["Sales Invoice", "Purchase Invoice", "Journal",
                 "Payment", "Accrual", "Depreciation"], n),
            "is_reversal": rng.random(n) < 0.021,
            "fiscal_period": ((ts.dt.month - 4) % 12 + 1).astype("int8"),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_accounts_receivable")
def accounts_receivable(rng, ctx, profile):
    cust_idx = ctx.customer.set_index("customer_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        customers = rng.choice(ctx.customer_ids, n)
        outstanding = rng.lognormal(11.0, 1.4, n)
        band = cust_idx.loc[customers, "credit_band"].to_numpy()
        age_bias = pd.Series(band).map({"A": 8, "B": 18, "C": 38, "D": 66}).to_numpy()
        age = (rng.gamma(1.7, 14, n) + age_bias).clip(0, 400)
        bucket = pd.cut(age, [-1, 30, 60, 90, 120, 10_000],
                        labels=["Current", "31-60", "61-90", "91-120", "120+"])
        df = pd.DataFrame({
            "ar_id": c.seq_ids("AR", offset, n),
            "snapshot_date": ts,
            "date_key": c.date_key(ts),
            "customer_id": customers,
            "invoice_id": c.seq_ids("INV", offset // 2, n, 12),
            "outstanding_zar": outstanding.round(2),
            "days_outstanding": age.round(0).astype("int16"),
            "ageing_bucket": bucket.astype(str),
            "credit_band": band,
            "provision_pct": np.select(
                [age <= 30, age <= 60, age <= 90, age <= 120],
                [0.0, 0.05, 0.20, 0.50], default=0.90),
            "is_doubtful": age > 90,
        })
        df["provision_zar"] = (df["outstanding_zar"] * df["provision_pct"]).round(2)
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_accounts_payable")
def accounts_payable(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        amount = rng.lognormal(11.4, 1.5, n)
        age = rng.gamma(1.9, 13, n).clip(0, 300)
        df = pd.DataFrame({
            "ap_id": c.seq_ids("AP", offset, n),
            "snapshot_date": ts,
            "date_key": c.date_key(ts),
            "supplier_id": rng.choice(ctx.supplier_ids, n),
            "outstanding_zar": amount.round(2),
            "days_outstanding": age.round(0).astype("int16"),
            "payment_terms_days": rng.choice([14, 30, 45, 60, 90], n,
                                             p=[0.10, 0.46, 0.22, 0.15, 0.07]),
            "is_overdue": age > 45,
            "early_settlement_discount_pct": np.where(
                rng.random(n) < 0.18, rng.uniform(0.005, 0.03, n), 0.0).round(4),
            "on_hold": rng.random(n) < 0.06,
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_capex")
def capex(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        budget = rng.lognormal(13.6, 1.1, n)
        spend = budget * rng.beta(4, 2.2, n) * 1.12
        df = pd.DataFrame({
            "capex_id": c.seq_ids("CAP", offset, n),
            "period_date": ts,
            "date_key": c.date_key(ts),
            "project_code": np.array([f"PRJ{x:05d}" for x in rng.integers(1, 4000, n)]),
            "site_id": rng.choice(ctx.site_ids, n),
            "capex_category": rng.choice(
                ["New Site Build", "Site Refurbishment", "Tank Replacement",
                 "EV Charging Rollout", "Solar Installation", "Terminal Upgrade",
                 "Fleet Renewal", "Digital Platform"], n,
                p=[0.11, 0.24, 0.13, 0.12, 0.09, 0.10, 0.13, 0.08]),
            "budget_zar": budget.round(2),
            "actual_spend_zar": spend.round(2),
            "variance_zar": (spend - budget).round(2),
            "variance_pct": ((spend / budget - 1) * 100).round(2),
            "expected_irr_pct": rng.normal(14.5, 5.5, n).clip(-5, 45).round(2),
            "payback_years": rng.gamma(3.0, 1.9, n).clip(0.5, 25).round(2),
            "project_status": rng.choice(
                ["Approved", "In Progress", "Completed", "On Hold"], n,
                p=[0.18, 0.34, 0.41, 0.07]),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_opex")
def opex(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        amount = rng.lognormal(11.2, 1.3, n)
        df = pd.DataFrame({
            "opex_id": c.seq_ids("OPX", offset, n),
            "period_date": ts,
            "date_key": c.date_key(ts),
            "cost_centre_code": rng.choice(
                ctx.cost_centre["cost_centre_code"].to_numpy(), n),
            "site_id": rng.choice(ctx.site_ids, n),
            "gl_account_code": rng.choice(
                ctx.gl_account.loc[ctx.gl_account["account_class"] == "Opex",
                                   "gl_account_code"].to_numpy(), n),
            "expense_category": rng.choice(
                ["Rent", "Utilities", "Salaries", "Maintenance", "Marketing",
                 "IT", "Insurance", "Professional Fees", "Transport"], n),
            "amount_zar": amount.round(2),
            "is_recurring": rng.random(n) < 0.68,
            "is_accrual": rng.random(n) < 0.14,
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_budget")
def budget(rng, ctx, profile):
    versions = np.array(["BUD-FY25", "BUD-FY26", "BUD-FY27", "BUD-FY26-R1"])

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        df = pd.DataFrame({
            "budget_id": c.seq_ids("BUD", offset, n),
            "period_date": ts,
            "date_key": c.date_key(ts),
            "budget_version_code": rng.choice(versions, n),
            "gl_account_code": rng.choice(
                ctx.gl_account["gl_account_code"].to_numpy(), n),
            "cost_centre_code": rng.choice(
                ctx.cost_centre["cost_centre_code"].to_numpy(), n),
            "business_unit_code": rng.choice(
                np.array([b[0] for b in ref.BUSINESS_UNITS]), n),
            "budget_amount_zar": rng.lognormal(12.6, 1.3, n).round(2),
            "budget_volume_litres": rng.lognormal(12.0, 1.5, n).round(1),
            "scenario_name": rng.choice(ref.SCENARIOS, n,
                                        p=[0.0, 0.55, 0.16, 0.19, 0.10]),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_forecast")
def forecast(rng, ctx, profile):
    versions = np.array([f"FC-{y}-{q}" for y in (2025, 2026)
                         for q in ("Q1", "Q2", "Q3", "Q4")])

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        base = rng.lognormal(12.7, 1.25, n)
        df = pd.DataFrame({
            "forecast_id": c.seq_ids("FCT", offset, n),
            "period_date": ts,
            "date_key": c.date_key(ts),
            "forecast_version_code": rng.choice(versions, n),
            "business_unit_code": rng.choice(
                np.array([b[0] for b in ref.BUSINESS_UNITS]), n),
            "site_id": rng.choice(ctx.site_ids, n),
            "product_id": rng.choice(ref.ROAD_FUEL_IDS, n),
            "forecast_volume_litres": base.round(1),
            "forecast_revenue_zar": (base * rng.uniform(21, 25, n)).round(2),
            "confidence_low_litres": (base * rng.uniform(0.80, 0.93, n)).round(1),
            "confidence_high_litres": (base * rng.uniform(1.07, 1.24, n)).round(1),
            "forecast_method": rng.choice(
                ["Statistical", "Driver Based", "Manual Override", "ML Model"], n,
                p=[0.34, 0.28, 0.14, 0.24]),
            "scenario_name": rng.choice(ref.SCENARIOS, n,
                                        p=[0.0, 0.52, 0.18, 0.20, 0.10]),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_budget_vs_actual")
def budget_vs_actual(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        bud = rng.lognormal(12.6, 1.25, n)
        act = bud * rng.normal(1.0, 0.16, n).clip(0.4, 1.8)
        df = pd.DataFrame({
            "bva_id": c.seq_ids("BVA", offset, n),
            "period_date": ts,
            "date_key": c.date_key(ts),
            "gl_account_code": rng.choice(
                ctx.gl_account["gl_account_code"].to_numpy(), n),
            "cost_centre_code": rng.choice(
                ctx.cost_centre["cost_centre_code"].to_numpy(), n),
            "business_unit_code": rng.choice(
                np.array([b[0] for b in ref.BUSINESS_UNITS]), n),
            "budget_amount_zar": bud.round(2),
            "actual_amount_zar": act.round(2),
            "variance_zar": (act - bud).round(2),
            "variance_pct": ((act / bud - 1) * 100).round(3),
            "is_favourable": act <= bud,
            "variance_explanation_required": np.abs(act / bud - 1) > 0.10,
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_cashflow")
def cashflow(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        inflow = rng.lognormal(13.2, 1.1, n)
        outflow = inflow * rng.normal(0.94, 0.14, n).clip(0.4, 1.7)
        df = pd.DataFrame({
            "cashflow_id": c.seq_ids("CF", offset, n),
            "period_date": ts,
            "date_key": c.date_key(ts),
            "legal_entity_code": np.array(
                [f"LE{x:02d}" for x in rng.integers(1, 13, n)]),
            "cashflow_category": rng.choice(
                ["Operating", "Investing", "Financing"], n, p=[0.68, 0.19, 0.13]),
            "inflow_zar": inflow.round(2),
            "outflow_zar": outflow.round(2),
            "net_cashflow_zar": (inflow - outflow).round(2),
            "closing_balance_zar": rng.lognormal(14.4, 0.9, n).round(2),
            "currency_code": rng.choice(["ZAR", "USD", "EUR"], n, p=[0.78, 0.16, 0.06]),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_working_capital")
def working_capital(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        dso = rng.gamma(6, 6.5, n).clip(5, 180)
        dio = rng.gamma(4, 3.4, n).clip(2, 90)
        dpo = rng.gamma(6, 7.2, n).clip(5, 160)
        df = pd.DataFrame({
            "working_capital_id": c.seq_ids("WC", offset, n),
            "period_date": ts,
            "date_key": c.date_key(ts),
            "legal_entity_code": np.array(
                [f"LE{x:02d}" for x in rng.integers(1, 13, n)]),
            "business_unit_code": rng.choice(
                np.array([b[0] for b in ref.BUSINESS_UNITS]), n),
            "receivables_zar": rng.lognormal(14.1, 0.9, n).round(2),
            "inventory_zar": rng.lognormal(13.7, 0.9, n).round(2),
            "payables_zar": rng.lognormal(13.9, 0.9, n).round(2),
            "days_sales_outstanding": dso.round(1),
            "days_inventory_outstanding": dio.round(1),
            "days_payables_outstanding": dpo.round(1),
            "cash_conversion_cycle_days": (dso + dio - dpo).round(1),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_daily_executive_kpi")
def daily_executive_kpi(rng, ctx, profile):
    site_idx = ctx.site.set_index("site_id")
    bu_codes = np.array([b[0] for b in ref.BUSINESS_UNITS])

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        sites = c.weighted_sites(rng, ctx, n)
        di = site_idx.loc[sites, "demand_index"].to_numpy()
        litres = rng.gamma(5.0, 1_500, n) * di
        revenue = litres * rng.uniform(22, 25, n)
        shop = revenue * rng.uniform(0.04, 0.14, n)
        margin = revenue * rng.uniform(0.055, 0.115, n) + shop * 0.42
        df = pd.DataFrame({
            "executive_kpi_id": c.seq_ids("EKP", offset, n),
            "business_date": ts,
            "date_key": c.date_key(ts),
            "site_id": sites,
            "business_unit_code": rng.choice(bu_codes, n),
            "province": site_idx.loc[sites, "province"].to_numpy(),
            "fuel_volume_litres": litres.round(1),
            "fuel_revenue_zar": revenue.round(2),
            "shop_revenue_zar": shop.round(2),
            "total_revenue_zar": (revenue + shop).round(2),
            "gross_margin_zar": margin.round(2),
            "gross_margin_pct": (margin / (revenue + shop) * 100).round(3),
            "customer_count": (litres / rng.uniform(40, 58, n)).astype("int32"),
            "average_transaction_zar": rng.normal(455, 120, n).clip(60, 3_000).round(2),
            "otif_pct": rng.beta(9, 1.6, n).round(4) * 100,
            "stock_availability_pct": rng.beta(24, 1.5, n).round(4) * 100,
            "safety_incidents": rng.poisson(0.03, n).astype("int16"),
            "nps_score": rng.normal(38, 16, n).clip(-100, 100).round(1),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk
