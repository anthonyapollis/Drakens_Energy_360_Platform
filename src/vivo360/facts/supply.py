"""Supply, procurement, terminal and inventory facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fact
from . import _common as c
from .. import reference as ref


@fact("fact_procurement_receipts")
def procurement_receipts(rng, ctx, profile):
    base_cost = {p.product_id: p.base_cost_zar for p in ref.PRODUCTS}

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        prods = rng.choice(ref.FUEL_IDS, n)
        qty = rng.lognormal(12.9, 0.85, n).clip(20_000, 12_000_000)
        unit = np.array([base_cost[p] for p in prods]) * rng.normal(0.94, 0.07, n)
        df = pd.DataFrame({
            "receipt_id": c.seq_ids("PR", offset, n),
            "receipt_ts": ts,
            "date_key": c.date_key(ts),
            "purchase_order_id": c.seq_ids("PO", offset // 2, n, 12),
            "supplier_id": rng.choice(ctx.supplier_ids, n),
            "terminal_id": rng.choice(ctx.terminal_ids, n),
            "product_id": prods,
            "quantity_litres": qty.round(2),
            "unit_cost_zar": unit.round(4),
            "total_cost_zar": (qty * unit).round(2),
            "source_mode": rng.choice(
                ["Import Vessel", "Refinery", "Pipeline", "Road", "Rail"], n,
                p=[0.31, 0.28, 0.19, 0.15, 0.07]),
            "quality_pass": rng.random(n) < 0.986,
            "density_kg_per_m3": rng.normal(835, 22, n).round(2),
            "temperature_celsius": rng.normal(23, 6, n).round(1),
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_procurement_orders")
def procurement_orders(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        qty = rng.lognormal(12.9, 0.9, n).clip(10_000, 14_000_000)
        df = pd.DataFrame({
            "purchase_order_id": c.seq_ids("PO", offset, n),
            "order_date": ts,
            "date_key": c.date_key(ts),
            "supplier_id": rng.choice(ctx.supplier_ids, n),
            "terminal_id": rng.choice(ctx.terminal_ids, n),
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "ordered_litres": qty.round(2),
            "expected_delivery_date": ts + pd.to_timedelta(
                rng.integers(2, 45, n), unit="D"),
            "incoterm": rng.choice(["FOB", "CIF", "DAP", "EXW"], n),
            "order_status": rng.choice(["Open", "Received", "Cancelled"], n,
                                       p=[0.14, 0.84, 0.02]),
            "contracted_price_zar": rng.normal(19.4, 2.2, n).round(3),
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_import_cargoes")
def import_cargoes(rng, ctx, profile):
    port_codes = ctx.port["port_code"].to_numpy()

    def make_chunk(offset, n):
        eta = c.uniform_timestamps(rng, n)
        demurrage_h = np.where(rng.random(n) < 0.78, rng.gamma(1.4, 6, n),
                               rng.gamma(2.6, 34, n))
        volume = rng.uniform(8_000_000, 92_000_000, n)
        df = pd.DataFrame({
            "cargo_id": c.seq_ids("CGO", offset, n),
            "eta_ts": eta,
            "date_key": c.date_key(eta),
            "discharge_port_code": rng.choice(port_codes, n),
            "supplier_id": rng.choice(ctx.supplier_ids, n),
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "cargo_volume_litres": volume.round(0),
            "discharge_hours": rng.normal(38, 12, n).clip(8, 120).round(1),
            "demurrage_hours": demurrage_h.round(1),
            "demurrage_cost_usd": (demurrage_h * rng.uniform(900, 2600, n)).round(2),
            "landed_cost_zar_per_litre": rng.normal(18.9, 1.6, n).round(4),
            "vessel_imo": [f"IMO{9000000 + x}" for x in rng.integers(1, 600, n)],
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_terminal_receipts")
def terminal_receipts(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        gross = rng.lognormal(12.6, 0.8, n).clip(15_000, 9_000_000)
        # Volumetric loss is small but non-zero and is a real control metric.
        loss_pct = np.abs(rng.normal(0.0011, 0.0016, n))
        df = pd.DataFrame({
            "terminal_receipt_id": c.seq_ids("TR", offset, n),
            "receipt_ts": ts,
            "date_key": c.date_key(ts),
            "terminal_id": rng.choice(ctx.terminal_ids, n),
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "supplier_id": rng.choice(ctx.supplier_ids, n),
            "gross_litres": gross.round(2),
            "net_litres_at_20c": (gross * rng.normal(0.9985, 0.004, n)).round(2),
            "loss_litres": (gross * loss_pct).round(2),
            "loss_pct": (loss_pct * 100).round(4),
            "receipt_mode": rng.choice(["Vessel", "Pipeline", "Rail", "Road"], n,
                                       p=[0.34, 0.29, 0.13, 0.24]),
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_terminal_issues")
def terminal_issues(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        litres = rng.lognormal(10.0, 0.8, n).clip(2_000, 60_000)
        df = pd.DataFrame({
            "terminal_issue_id": c.seq_ids("TI", offset, n),
            "issue_ts": ts,
            "date_key": c.date_key(ts),
            "terminal_id": rng.choice(ctx.terminal_ids, n),
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "vehicle_id": rng.choice(ctx.vehicle_ids, n),
            "gantry_bay": rng.integers(1, 17, n).astype("int8"),
            "issued_litres": litres.round(2),
            "loading_minutes": rng.normal(42, 14, n).clip(8, 220).round(1),
            "queue_minutes": rng.gamma(1.7, 15, n).clip(0, 400).round(1),
            "destination_site_id": rng.choice(ctx.site_ids, n),
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_terminal_throughput")
def terminal_throughput(rng, ctx, profile):
    term = ctx.terminal.set_index("terminal_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        terms = rng.choice(ctx.terminal_ids, n)
        cap = term.loc[terms, "capacity_litres"].to_numpy()
        receipts = cap * rng.beta(1.6, 9, n)
        issues = receipts * rng.normal(0.98, 0.08, n).clip(0.6, 1.35)
        closing = cap * rng.beta(3.0, 2.4, n)
        df = pd.DataFrame({
            "throughput_id": c.seq_ids("TT", offset, n),
            "business_date": ts,
            "date_key": c.date_key(ts),
            "terminal_id": terms,
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "opening_stock_litres": (closing * rng.uniform(0.85, 1.15, n)).round(1),
            "receipts_litres": receipts.round(1),
            "issues_litres": issues.round(1),
            "closing_stock_litres": closing.round(1),
            "capacity_litres": cap,
            "utilisation_pct": (closing / cap * 100).round(2),
            "days_of_cover": (closing / np.maximum(issues, 1) ).clip(0, 90).round(2),
            "gain_loss_litres": rng.normal(0, 900, n).round(1),
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_inventory_snapshot")
def inventory_snapshot(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        is_site = rng.random(n) < 0.75
        cap = np.where(is_site,
                       rng.choice([9000, 12000, 23000, 30000, 46000], n).astype(float),
                       rng.uniform(400_000, 8_000_000, n))
        fill = rng.beta(2.6, 2.0, n)
        stock = cap * fill
        daily_use = np.maximum(cap * rng.uniform(0.04, 0.35, n), 1.0)
        df = pd.DataFrame({
            "snapshot_id": c.seq_ids("INV", offset, n),
            "snapshot_ts": ts,
            "date_key": c.date_key(ts),
            "location_type": np.where(is_site, "Site", "Terminal"),
            "site_id": np.where(is_site, rng.choice(ctx.site_ids, n), None),
            "terminal_id": np.where(is_site, None, rng.choice(ctx.terminal_ids, n)),
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "capacity_litres": cap.round(1),
            "stock_on_hand_litres": stock.round(2),
            "ullage_litres": (cap - stock).round(2),
            "fill_pct": (fill * 100).round(2),
            "average_daily_usage_litres": daily_use.round(2),
            "days_of_cover": (stock / daily_use).round(2),
            "is_stock_out_risk": (stock / daily_use) < 1.5,
            "reorder_point_litres": (daily_use * 2.5).round(2),
        })
        return c.add_audit_columns(df, "SRC03")

    return make_chunk


@fact("fact_inventory_movements")
def inventory_movements(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        mtype = rng.choice(
            ["Receipt", "Issue", "Transfer In", "Transfer Out", "Adjustment"],
            n, p=[0.24, 0.44, 0.11, 0.11, 0.10])
        qty = rng.lognormal(9.4, 1.2, n).clip(10, 900_000)
        signed = np.where(np.isin(mtype, ["Issue", "Transfer Out"]), -qty, qty)
        df = pd.DataFrame({
            "movement_id": c.seq_ids("MOV", offset, n),
            "movement_ts": ts,
            "date_key": c.date_key(ts),
            "movement_type": mtype,
            "site_id": rng.choice(ctx.site_ids, n),
            "terminal_id": rng.choice(ctx.terminal_ids, n),
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "quantity_litres": qty.round(2),
            "signed_quantity_litres": signed.round(2),
            "reason_code": rng.choice(ref.REASON_CODES, n),
            "posted_by_employee_id": rng.choice(ctx.employee["employee_id"].to_numpy(), n),
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_inventory_adjustments")
def inventory_adjustments(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        book = rng.uniform(4_000, 900_000, n)
        variance = book * rng.normal(0, 0.006, n)
        df = pd.DataFrame({
            "adjustment_id": c.seq_ids("ADJ", offset, n),
            "adjustment_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": rng.choice(ctx.site_ids, n),
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "book_stock_litres": book.round(2),
            "physical_stock_litres": (book + variance).round(2),
            "variance_litres": variance.round(2),
            "variance_pct": (variance / book * 100).round(4),
            "adjustment_reason": rng.choice(
                ["Temperature Correction", "Meter Error", "Evaporation",
                 "Data Entry Error", "Unexplained Loss", "Theft Suspected"], n,
                p=[0.30, 0.19, 0.17, 0.16, 0.14, 0.04]),
            "requires_investigation": np.abs(variance / book) > 0.005,
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_stock_losses")
def stock_losses(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        litres = rng.gamma(1.8, 320, n).clip(1, 60_000)
        df = pd.DataFrame({
            "stock_loss_id": c.seq_ids("SL", offset, n),
            "loss_date": ts,
            "date_key": c.date_key(ts),
            "site_id": rng.choice(ctx.site_ids, n),
            "terminal_id": rng.choice(ctx.terminal_ids, n),
            "product_id": rng.choice(ref.FUEL_IDS, n),
            "loss_litres": litres.round(2),
            "loss_value_zar": (litres * rng.uniform(18, 25, n)).round(2),
            "loss_category": rng.choice(
                ["Evaporation", "Leak", "Overfill Spill", "Theft",
                 "Meter Variance", "Contamination"], n,
                p=[0.34, 0.16, 0.12, 0.09, 0.22, 0.07]),
            "is_recoverable": rng.random(n) < 0.22,
            "insurance_claim_raised": rng.random(n) < 0.08,
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_replenishment_orders")
def replenishment_orders(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        qty = rng.choice([8000, 12000, 18000, 24000, 32000, 40000], n).astype(float)
        df = pd.DataFrame({
            "replenishment_id": c.seq_ids("REP", offset, n),
            "raised_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "terminal_id": rng.choice(ctx.terminal_ids, n),
            "product_id": rng.choice(ref.ROAD_FUEL_IDS, n),
            "requested_litres": qty,
            "trigger_type": rng.choice(
                ["Auto Replenishment", "Forecast Driven", "Manual", "Emergency"], n,
                p=[0.56, 0.24, 0.15, 0.05]),
            "days_of_cover_at_raise": rng.gamma(2.0, 1.1, n).clip(0.1, 12).round(2),
            "promised_delivery_ts": ts + pd.to_timedelta(
                rng.integers(4, 72, n), unit="h"),
            "fulfilled_flag": rng.random(n) < 0.955,
        })
        return c.add_audit_columns(df, "SRC03")

    return make_chunk
