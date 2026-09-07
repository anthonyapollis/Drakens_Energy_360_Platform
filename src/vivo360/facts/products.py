"""LPG, lubricants, aviation and marine facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import reference as ref
from . import _common as c
from . import fact


# ------------------------------------------------------------------ LPG
@fact("fact_lpg_sales")
def lpg_sales(rng, ctx, profile):
    price = {p.product_id: p.base_price_zar for p in ref.PRODUCTS}
    cost = {p.product_id: p.base_cost_zar for p in ref.PRODUCTS}
    lpg_sites = ctx.site.loc[ctx.site["has_lpg"], "site_id"].to_numpy()
    if len(lpg_sites) == 0:
        lpg_sites = ctx.site_ids

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        prods = rng.choice(ref.LPG_IDS, n, p=[0.22, 0.44, 0.26, 0.08])
        # Winter cooking and heating demand is materially higher.
        month = ts.dt.month.to_numpy()
        winter = np.isin(month, [5, 6, 7, 8])
        kg = np.where(np.isin(prods, ["LPG02"]), 9.0,
             np.where(prods == "LPG03", 19.0,
             np.where(prods == "LPG04", 48.0, rng.gamma(2.0, 260, n).clip(20, 24_000))))
        kg = kg * rng.choice([1, 1, 1, 2], n) * np.where(winter, 1.28, 1.0)
        unit = np.array([price[p] for p in prods]) * rng.normal(1.0, 0.05, n)
        unit_cost = np.array([cost[p] for p in prods]) * rng.normal(1.0, 0.04, n)
        rev = kg * unit
        df = pd.DataFrame({
            "lpg_sale_id": c.seq_ids("LP", offset, n),
            "sale_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": rng.choice(lpg_sites, n),
            "customer_id": np.where(rng.random(n) < 0.35,
                                    rng.choice(ctx.customer_ids, n), None),
            "product_id": prods,
            "cylinder_type_code": pd.Series(prods).map(
                {"LPG01": "BULK", "LPG02": "C9", "LPG03": "C19", "LPG04": "C48"}
            ).to_numpy(),
            "quantity_kg": kg.round(3),
            "unit_price_zar": unit.round(3),
            "revenue_zar": rev.round(2),
            "cogs_zar": (kg * unit_cost).round(2),
            "gross_margin_zar": (rev - kg * unit_cost).round(2),
            "channel": rng.choice(["Retail Cylinder", "Commercial Bulk", "Distributor"],
                                  n, p=[0.62, 0.23, 0.15]),
            "is_winter_peak": winter,
        })
        return c.add_audit_columns(df, "SRC02")

    return make_chunk


@fact("fact_lpg_cylinder_movements")
def lpg_cylinder_movements(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        mtype = rng.choice(["Issued Full", "Returned Empty", "Refilled",
                            "Scrapped", "Transferred"], n,
                           p=[0.38, 0.34, 0.20, 0.02, 0.06])
        df = pd.DataFrame({
            "cylinder_movement_id": c.seq_ids("LCM", offset, n),
            "movement_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": rng.choice(ctx.site_ids, n),
            "depot_id": rng.choice(ctx.depot["depot_id"].to_numpy(), n),
            "cylinder_type_code": rng.choice(["C9", "C19", "C48"], n, p=[0.6, 0.31, 0.09]),
            "movement_type": mtype,
            "cylinder_count": rng.integers(1, 260, n).astype("int16"),
            "deposit_value_zar": rng.uniform(0, 32_000, n).round(2),
            "requires_requalification": rng.random(n) < 0.07,
        })
        return c.add_audit_columns(df, "SRC14")

    return make_chunk


@fact("fact_lpg_bulk_deliveries")
def lpg_bulk_deliveries(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n, hourly=False)
        kg = rng.lognormal(8.6, 0.85, n).clip(200, 60_000)
        df = pd.DataFrame({
            "lpg_delivery_id": c.seq_ids("LBD", offset, n),
            "delivery_ts": ts,
            "date_key": c.date_key(ts),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "depot_id": rng.choice(ctx.depot["depot_id"].to_numpy(), n),
            "vehicle_id": rng.choice(ctx.vehicle_ids, n),
            "delivered_kg": kg.round(2),
            "tank_fill_pct_before": rng.uniform(5, 55, n).round(1),
            "tank_fill_pct_after": rng.uniform(70, 96, n).round(1),
            "revenue_zar": (kg * rng.uniform(26, 33, n)).round(2),
            "is_emergency_delivery": rng.random(n) < 0.09,
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_lpg_inventory_snapshot")
def lpg_inventory_snapshot(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        cap = rng.choice([2_000, 5_000, 12_000, 25_000], n).astype(float)
        stock = cap * rng.beta(2.5, 2.0, n)
        df = pd.DataFrame({
            "lpg_snapshot_id": c.seq_ids("LPI", offset, n),
            "snapshot_ts": ts,
            "date_key": c.date_key(ts),
            "depot_id": rng.choice(ctx.depot["depot_id"].to_numpy(), n),
            "site_id": rng.choice(ctx.site_ids, n),
            "capacity_kg": cap,
            "stock_on_hand_kg": stock.round(2),
            "cylinders_full": rng.integers(0, 1400, n).astype("int32"),
            "cylinders_empty": rng.integers(0, 1800, n).astype("int32"),
            "days_of_cover": (stock / np.maximum(cap * 0.12, 1)).round(2),
        })
        return c.add_audit_columns(df, "SRC03")

    return make_chunk


# ------------------------------------------------------------ lubricants
@fact("fact_lubricant_sales")
def lubricant_sales(rng, ctx, profile):
    price = {p.product_id: p.base_price_zar for p in ref.PRODUCTS}
    cost = {p.product_id: p.base_cost_zar for p in ref.PRODUCTS}

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        prods = rng.choice(ref.LUBE_IDS, n)
        litres = rng.choice([1, 4, 5, 20, 25, 208], n,
                            p=[0.30, 0.19, 0.17, 0.19, 0.10, 0.05]).astype(float)
        litres = litres * rng.integers(1, 4, n)
        unit = np.array([price[p] for p in prods]) * rng.normal(1.0, 0.08, n)
        unit_cost = np.array([cost[p] for p in prods]) * rng.normal(1.0, 0.05, n)
        rev = litres * unit
        cogs = litres * unit_cost
        df = pd.DataFrame({
            "lubricant_sale_id": c.seq_ids("LU", offset, n),
            "sale_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": rng.choice(ctx.site_ids, n),
            "customer_id": np.where(rng.random(n) < 0.46,
                                    rng.choice(ctx.customer_ids, n), None),
            "product_id": prods,
            "channel": rng.choice(
                ["Retail Forecourt", "Commercial Direct", "Distributor", "Wholesale"],
                n, p=[0.31, 0.34, 0.24, 0.11]),
            "quantity_litres": litres.round(2),
            "unit_price_zar": unit.round(2),
            "revenue_zar": rev.round(2),
            "cogs_zar": cogs.round(2),
            "gross_margin_zar": (rev - cogs).round(2),
            "gross_margin_pct": ((rev - cogs) / rev * 100).round(2),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_lubricant_orders")
def lubricant_orders(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        litres = rng.lognormal(5.6, 1.3, n).clip(1, 40_000)
        df = pd.DataFrame({
            "lubricant_order_id": c.seq_ids("LUO", offset, n),
            "order_date": ts,
            "date_key": c.date_key(ts),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "warehouse_id": np.array([f"WH{x:04d}" for x in rng.integers(1, 61, n)]),
            "product_id": rng.choice(ref.LUBE_IDS, n),
            "ordered_litres": litres.round(2),
            "fulfilled_litres": (litres * rng.uniform(0.85, 1.0, n)).round(2),
            "order_status": rng.choice(ref.ORDER_STATUSES, n,
                                       p=[0.02, 0.06, 0.06, 0.70, 0.06, 0.02, 0.08]),
            "lead_time_days": rng.gamma(2.0, 2.4, n).clip(0, 40).round(1),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_lubricant_inventory_snapshot")
def lubricant_inventory_snapshot(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        stock = rng.gamma(2.4, 900, n).clip(0, 90_000)
        df = pd.DataFrame({
            "lubricant_snapshot_id": c.seq_ids("LUI", offset, n),
            "snapshot_ts": ts,
            "date_key": c.date_key(ts),
            "warehouse_id": np.array([f"WH{x:04d}" for x in rng.integers(1, 61, n)]),
            "product_id": rng.choice(ref.LUBE_IDS, n),
            "stock_on_hand_litres": stock.round(2),
            "stock_value_zar": (stock * rng.uniform(45, 80, n)).round(2),
            "pallet_positions_used": (stock / 800).round(1),
            "days_of_cover": rng.gamma(3.0, 12, n).clip(0, 220).round(1),
            "is_slow_moving": rng.random(n) < 0.18,
        })
        return c.add_audit_columns(df, "SRC12")

    return make_chunk


# -------------------------------------------------------------- aviation
@fact("fact_aviation_sales")
def aviation_sales(rng, ctx, profile):
    airports = ctx.airport["iata_code"].to_numpy()

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        litres = rng.lognormal(9.6, 1.15, n).clip(180, 260_000)
        price = rng.normal(19.8, 1.4, n).clip(14, 28)
        rev = litres * price
        df = pd.DataFrame({
            "aviation_sale_id": c.seq_ids("AV", offset, n),
            "sale_ts": ts,
            "date_key": c.date_key(ts),
            "airport_code": rng.choice(airports, n,
                                       p=_airport_p(len(airports))),
            "airline_code": np.array([f"SY{x:02d}" for x in rng.integers(1, 19, n)]),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "product_id": rng.choice(["F005", "F009"], n, p=[0.94, 0.06]),
            "uplift_litres": litres.round(2),
            "unit_price_zar": price.round(3),
            "revenue_zar": rev.round(2),
            "cogs_zar": (rev * rng.uniform(0.86, 0.94, n)).round(2),
            "flight_type": rng.choice(["Commercial", "Cargo", "Charter", "Government"],
                                      n, p=[0.72, 0.14, 0.10, 0.04]),
            "is_into_plane": rng.random(n) < 0.88,
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_aircraft_uplifts")
def aircraft_uplifts(rng, ctx, profile):
    airports = ctx.airport["iata_code"].to_numpy()

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        litres = rng.lognormal(9.4, 1.1, n).clip(150, 240_000)
        df = pd.DataFrame({
            "uplift_id": c.seq_ids("UPL", offset, n),
            "uplift_ts": ts,
            "date_key": c.date_key(ts),
            "airport_code": rng.choice(airports, n),
            "airline_code": np.array([f"SY{x:02d}" for x in rng.integers(1, 19, n)]),
            "flight_number": [f"SY{x:04d}" for x in rng.integers(1, 9999, n)],
            "aircraft_registration": [f"ZS-SYN{x:03d}" for x in rng.integers(1, 400, n)],
            "uplift_litres": litres.round(2),
            "uplift_duration_minutes": rng.normal(24, 9, n).clip(4, 120).round(1),
            "density_kg_per_litre": rng.normal(0.795, 0.008, n).round(4),
            "meter_start": rng.uniform(0, 9_000_000, n).round(1),
            "quality_check_passed": rng.random(n) < 0.994,
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_aviation_inventory_snapshot")
def aviation_inventory_snapshot(rng, ctx, profile):
    airports = ctx.airport["iata_code"].to_numpy()

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        cap = rng.choice([500_000, 1_200_000, 3_000_000, 8_000_000], n).astype(float)
        stock = cap * rng.beta(2.8, 2.0, n)
        df = pd.DataFrame({
            "aviation_snapshot_id": c.seq_ids("AVI", offset, n),
            "snapshot_ts": ts,
            "date_key": c.date_key(ts),
            "airport_code": rng.choice(airports, n),
            "product_id": "F005",
            "capacity_litres": cap,
            "stock_on_hand_litres": stock.round(1),
            "days_of_cover": (stock / np.maximum(cap * 0.18, 1)).round(2),
            "water_ppm": rng.gamma(1.4, 6, n).clip(0, 60).round(1),
            "on_specification": rng.random(n) < 0.991,
        })
        return c.add_audit_columns(df, "SRC03")

    return make_chunk


# ---------------------------------------------------------------- marine
@fact("fact_marine_sales")
def marine_sales(rng, ctx, profile):
    ports = ctx.port["port_code"].to_numpy()

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n, hourly=False)
        litres = rng.lognormal(11.6, 1.25, n).clip(3_000, 3_000_000)
        price = rng.normal(17.4, 1.6, n).clip(11, 26)
        rev = litres * price
        df = pd.DataFrame({
            "marine_sale_id": c.seq_ids("MR", offset, n),
            "sale_ts": ts,
            "date_key": c.date_key(ts),
            "port_code": rng.choice(ports, n, p=_port_p(len(ports))),
            "customer_id": rng.choice(ctx.customer_ids, n),
            "vessel_imo": [f"IMO{9000000 + x}" for x in rng.integers(1, 600, n)],
            "product_id": rng.choice(["F006", "F007"], n, p=[0.42, 0.58]),
            "bunker_litres": litres.round(2),
            "unit_price_zar": price.round(3),
            "revenue_zar": rev.round(2),
            "cogs_zar": (rev * rng.uniform(0.87, 0.95, n)).round(2),
            "vessel_class": rng.choice(
                ["Container", "Bulk Carrier", "Tanker", "Fishing", "Naval", "Offshore"],
                n, p=[0.30, 0.26, 0.18, 0.14, 0.04, 0.08]),
            "sulphur_pct": rng.choice([0.10, 0.50], n, p=[0.62, 0.38]),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_bunker_deliveries")
def bunker_deliveries(rng, ctx, profile):
    ports = ctx.port["port_code"].to_numpy()

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        litres = rng.lognormal(11.4, 1.2, n).clip(2_000, 2_600_000)
        df = pd.DataFrame({
            "bunker_delivery_id": c.seq_ids("BNK", offset, n),
            "delivery_ts": ts,
            "date_key": c.date_key(ts),
            "port_code": rng.choice(ports, n),
            "vessel_imo": [f"IMO{9000000 + x}" for x in rng.integers(1, 600, n)],
            "delivery_mode": rng.choice(["Barge", "Truck", "Pipeline"], n,
                                        p=[0.56, 0.30, 0.14]),
            "delivered_litres": litres.round(2),
            "pumping_rate_lpm": rng.normal(4200, 1100, n).clip(400, 12_000).round(0),
            "delivery_hours": rng.gamma(2.4, 3.1, n).clip(0.4, 40).round(2),
            "bunker_delivery_note_signed": rng.random(n) < 0.985,
            "quantity_dispute_raised": rng.random(n) < 0.023,
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_marine_inventory_snapshot")
def marine_inventory_snapshot(rng, ctx, profile):
    ports = ctx.port["port_code"].to_numpy()

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        cap = rng.choice([1_000_000, 4_000_000, 9_000_000], n).astype(float)
        stock = cap * rng.beta(2.4, 2.2, n)
        df = pd.DataFrame({
            "marine_snapshot_id": c.seq_ids("MRI", offset, n),
            "snapshot_ts": ts,
            "date_key": c.date_key(ts),
            "port_code": rng.choice(ports, n),
            "product_id": rng.choice(["F006", "F007"], n),
            "capacity_litres": cap,
            "stock_on_hand_litres": stock.round(1),
            "days_of_cover": (stock / np.maximum(cap * 0.14, 1)).round(2),
            "viscosity_cst": rng.normal(180, 60, n).clip(20, 400).round(1),
        })
        return c.add_audit_columns(df, "SRC03")

    return make_chunk


def _airport_p(k):
    # Traffic is heavily concentrated at the three largest airports.
    p = np.full(k, 0.30 / max(1, k - 3))
    p[:3] = [0.34, 0.22, 0.14]
    return p / p.sum()


def _port_p(k):
    p = np.full(k, 0.28 / max(1, k - 3))
    p[:3] = [0.36, 0.20, 0.16]
    return p / p.sum()
