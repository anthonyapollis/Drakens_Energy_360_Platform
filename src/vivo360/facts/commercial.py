"""Commercial / B2B facts: orders, deliveries, contracts, invoicing, credit."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fact
from . import _common as c
from .. import reference as ref


@fact("fact_commercial_orders")
def commercial_orders(rng, ctx, profile):
    cust = ctx.customer
    cust_ids = cust["customer_id"].to_numpy()
    # Larger accounts order far more often and in bigger volumes.
    w = cust["revenue_index"].to_numpy(dtype=float)
    w = w / w.sum()
    cust_idx = cust.set_index("customer_id")
    base_price = {p.product_id: p.base_price_zar for p in ref.PRODUCTS}
    comm_products = np.array(ref.ROAD_FUEL_IDS + ref.LUBE_IDS)

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n, hourly=False)
        customers = rng.choice(cust_ids, n, p=w)
        cu = cust_idx.loc[customers]
        ri = cu["revenue_index"].to_numpy()

        prods = rng.choice(comm_products, n)
        litres = rng.lognormal(8.1, 0.95, n) * np.sqrt(ri)
        litres = litres.clip(200, 2_500_000)

        list_price = np.array([base_price[p] for p in prods])
        discount_cpl = rng.gamma(2.0, 16.0, n).clip(0, 210) / 100.0
        net_price = (list_price - discount_cpl).clip(1.0, None)
        revenue = litres * net_price
        cogs = revenue * rng.uniform(0.86, 0.955, n)

        status = rng.choice(ref.ORDER_STATUSES, n,
                            p=[0.02, 0.05, 0.05, 0.72, 0.05, 0.02, 0.09])
        df = pd.DataFrame({
            "order_id": c.seq_ids("CO", offset, n),
            "order_ts": ts,
            "date_key": c.date_key(ts),
            "customer_id": customers,
            "contract_id": np.where(
                rng.random(n) < 0.68,
                rng.choice(ctx.contract["contract_id"].to_numpy(), n), None),
            "product_id": prods,
            "sector": cu["sector"].to_numpy(),
            "segment": cu["segment"].to_numpy(),
            "channel": rng.choice(ref.CHANNELS, n, p=[0.03, 0.58, 0.24, 0.05, 0.10]),
            "volume_litres": litres.round(2),
            "list_price_zar": list_price.round(3),
            "discount_cents_per_litre": (discount_cpl * 100).round(1),
            "net_price_zar": net_price.round(3),
            "revenue_zar": revenue.round(2),
            "cogs_zar": cogs.round(2),
            "gross_margin_zar": (revenue - cogs).round(2),
            "order_status": status,
            "requested_delivery_date": (ts + pd.to_timedelta(
                rng.integers(1, 15, n), unit="D")).dt.normalize(),
            "payment_terms_days": cu["payment_terms_days"].to_numpy(),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_commercial_order_lines")
def commercial_order_lines(rng, ctx, profile):
    comm_products = np.array(ref.ROAD_FUEL_IDS + ref.LUBE_IDS + ref.LPG_IDS)
    base_price = {p.product_id: p.base_price_zar for p in ref.PRODUCTS}

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n, hourly=False)
        prods = rng.choice(comm_products, n)
        litres = rng.lognormal(7.6, 1.05, n).clip(50, 900_000)
        price = np.array([base_price[p] for p in prods]) * rng.normal(0.97, 0.05, n)
        df = pd.DataFrame({
            "order_line_id": c.seq_ids("COL", offset, n),
            "order_id": c.seq_ids("CO", offset // 2, n, 12),
            "line_number": rng.integers(1, 7, n).astype("int8"),
            "order_ts": ts,
            "date_key": c.date_key(ts),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "product_id": prods,
            "ordered_quantity": litres.round(2),
            "delivered_quantity": (litres * rng.uniform(0.93, 1.0, n)).round(2),
            "unit_price_zar": price.round(3),
            "line_revenue_zar": (litres * price).round(2),
            "line_status": rng.choice(["Delivered", "Partial", "Cancelled"], n,
                                      p=[0.93, 0.055, 0.015]),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_commercial_deliveries")
def commercial_deliveries(rng, ctx, profile):
    def make_chunk(offset, n):
        planned = c.sample_timestamps(rng, n, hourly=False)
        # Most deliveries are close to plan; a heavy tail creates late cases.
        delay = np.where(rng.random(n) < 0.82,
                         rng.normal(8, 26, n),
                         rng.gamma(2.2, 95, n))
        actual = planned + pd.to_timedelta(delay.round(0), unit="m")
        ordered = rng.lognormal(8.3, 0.9, n).clip(500, 900_000)
        delivered = ordered * np.where(rng.random(n) < 0.94, 1.0,
                                       rng.uniform(0.75, 0.99, n))
        df = pd.DataFrame({
            "commercial_delivery_id": c.seq_ids("CD", offset, n),
            "planned_delivery_ts": planned,
            "actual_delivery_ts": actual,
            "date_key": c.date_key(planned),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "order_id": c.seq_ids("CO", offset // 2, n, 12),
            "product_id": rng.choice(ref.ROAD_FUEL_IDS, n),
            "vehicle_id": rng.choice(ctx.vehicle_ids, n),
            "ordered_litres": ordered.round(2),
            "delivered_litres": delivered.round(2),
            "delay_minutes": delay.round(0).astype("int32"),
            "is_on_time": delay <= 60,
            "is_in_full": delivered >= ordered * 0.995,
            "otif_flag": (delay <= 60) & (delivered >= ordered * 0.995),
            "delivery_status": rng.choice(ref.DELIVERY_STATUSES, n,
                                          p=[0.01, 0.02, 0.02, 0.88, 0.05, 0.02]),
            "failure_reason_code": rng.choice(ref.REASON_CODES, n,
                                              p=_reason_probs()),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_contract_volume_commitments")
def contract_volume_commitments(rng, ctx, profile):
    contract_ids = ctx.contract["contract_id"].to_numpy()

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        committed = rng.lognormal(12.0, 1.2, n)
        achieved = committed * rng.beta(6, 2.2, n) * 1.15
        df = pd.DataFrame({
            "commitment_id": c.seq_ids("CVC", offset, n),
            "period_start_date": ts,
            "date_key": c.date_key(ts),
            "contract_id": rng.choice(contract_ids, n),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "product_id": rng.choice(ref.ROAD_FUEL_IDS, n),
            "committed_litres": committed.round(2),
            "achieved_litres": achieved.round(2),
            "achievement_pct": (achieved / committed * 100).round(2),
            "is_shortfall": achieved < committed,
            "shortfall_penalty_zar": np.where(
                achieved < committed,
                (committed - achieved) * rng.uniform(0.05, 0.4, n), 0.0).round(2),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_contract_pricing")
def contract_pricing(rng, ctx, profile):
    base_price = {p.product_id: p.base_price_zar for p in ref.PRODUCTS}

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        prods = rng.choice(ref.ROAD_FUEL_IDS, n)
        bfp = np.array([base_price[p] for p in prods]) * rng.normal(0.88, 0.04, n)
        disc = rng.gamma(2.0, 18, n).clip(0, 220) / 100
        df = pd.DataFrame({
            "contract_price_id": c.seq_ids("CPR", offset, n),
            "effective_date": ts,
            "date_key": c.date_key(ts),
            "contract_id": rng.choice(ctx.contract["contract_id"].to_numpy(), n),
            "product_id": prods,
            "basic_fuel_price_zar": bfp.round(3),
            "differential_cents_per_litre": rng.normal(0, 30, n).round(1),
            "discount_cents_per_litre": (disc * 100).round(1),
            "net_contract_price_zar": (bfp - disc).round(3),
            "price_mechanism": rng.choice(
                ["Basic Fuel Price Linked", "Fixed", "Index Linked", "Cost Plus"], n),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_customer_invoices")
def customer_invoices(rng, ctx, profile):
    cust_idx = ctx.customer.set_index("customer_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        customers = rng.choice(ctx.customer_ids, n)
        terms = cust_idx.loc[customers, "payment_terms_days"].to_numpy()
        net = rng.lognormal(10.9, 1.35, n).clip(120, 40_000_000)
        vat = net * 0.15
        due = ts + pd.to_timedelta(terms, unit="D")
        # Days-sales-outstanding behaviour varies by credit band.
        band = cust_idx.loc[customers, "credit_band"].to_numpy()
        late_bias = pd.Series(band).map({"A": -3, "B": 2, "C": 11, "D": 26}).to_numpy()
        paid_delay = rng.gamma(1.6, 9, n) + late_bias
        df = pd.DataFrame({
            "invoice_id": c.seq_ids("INV", offset, n),
            "invoice_date": ts,
            "date_key": c.date_key(ts),
            "customer_id": customers,
            "due_date": due,
            "net_amount_zar": net.round(2),
            "vat_amount_zar": vat.round(2),
            "gross_amount_zar": (net + vat).round(2),
            "payment_terms_days": terms.astype("int16"),
            "days_to_payment": paid_delay.round(0).astype("int32"),
            "is_overdue": paid_delay > terms,
            "credit_band": band,
            "invoice_status": rng.choice(["Paid", "Open", "Overdue", "Disputed"], n,
                                         p=[0.78, 0.12, 0.08, 0.02]),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_customer_receipts")
def customer_receipts(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        df = pd.DataFrame({
            "receipt_id": c.seq_ids("RCP", offset, n),
            "receipt_date": ts,
            "date_key": c.date_key(ts),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "invoice_id": c.seq_ids("INV", offset // 2, n, 12),
            "amount_received_zar": rng.lognormal(10.8, 1.3, n).round(2),
            "payment_channel": rng.choice(
                ["EFT", "Debit Order", "Card", "Cash", "Cheque"], n,
                p=[0.58, 0.24, 0.10, 0.07, 0.01]),
            "is_partial_payment": rng.random(n) < 0.14,
            "allocated_flag": rng.random(n) < 0.93,
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_customer_credit_exposure")
def customer_credit_exposure(rng, ctx, profile):
    cust_idx = ctx.customer.set_index("customer_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        customers = rng.choice(ctx.customer_ids, n)
        limit = cust_idx.loc[customers, "credit_limit_zar"].to_numpy()
        used = limit * rng.beta(2.6, 2.0, n)
        df = pd.DataFrame({
            "exposure_id": c.seq_ids("CE", offset, n),
            "snapshot_date": ts,
            "date_key": c.date_key(ts),
            "customer_id": customers,
            "credit_limit_zar": limit.round(2),
            "outstanding_balance_zar": used.round(2),
            "utilisation_pct": (used / np.maximum(limit, 1) * 100).round(2),
            "overdue_balance_zar": (used * rng.beta(1.2, 9, n)).round(2),
            "days_sales_outstanding": rng.gamma(3.4, 11, n).clip(0, 210).round(1),
            "is_over_limit": used > limit,
            "credit_band": cust_idx.loc[customers, "credit_band"].to_numpy(),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


@fact("fact_customer_service_cases")
def customer_service_cases(rng, ctx, profile):
    def make_chunk(offset, n):
        opened = c.uniform_timestamps(rng, n)
        resolve_h = rng.gamma(1.9, 22, n)
        df = pd.DataFrame({
            "case_id": c.seq_ids("CS", offset, n),
            "opened_ts": opened,
            "date_key": c.date_key(opened),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "case_type": rng.choice(
                ["Delivery Delay", "Invoice Query", "Product Quality",
                 "Pricing Dispute", "Volume Shortfall", "General Enquiry"], n,
                p=[0.26, 0.24, 0.10, 0.14, 0.11, 0.15]),
            "priority": rng.choice(["Low", "Medium", "High", "Critical"], n,
                                   p=[0.34, 0.42, 0.19, 0.05]),
            "resolution_hours": resolve_h.round(2),
            "resolved_ts": opened + pd.to_timedelta(resolve_h.round(1), unit="h"),
            "is_resolved": rng.random(n) < 0.91,
            "breached_sla": resolve_h > 48,
            "satisfaction_score": rng.integers(1, 6, n).astype("int8"),
        })
        return c.add_audit_columns(df, "SRC09")

    return make_chunk


def _reason_probs():
    p = np.array([0.05, 0.07, 0.13, 0.05, 0.04, 0.03, 0.05, 0.03, 0.55])
    return p / p.sum()
