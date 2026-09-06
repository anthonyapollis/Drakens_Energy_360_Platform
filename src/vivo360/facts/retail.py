"""Retail and forecourt facts.

Grain notes:
  fact_retail_fuel_sales    one row per fuel sales transaction line
  fact_shop_sales           one row per convenience transaction line
  fact_forecourt_shift      one row per site/shift
  fact_pump_meter_readings  one row per pump/reading timestamp
  fact_tank_dips            one row per tank/dip timestamp
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fact
from . import _common as c
from .. import reference as ref


@fact("fact_retail_fuel_sales")
def retail_fuel_sales(rng, ctx, profile):
    # Forecourt grades: the four road fuels plus paraffin, which is still a
    # meaningful retail line in South Africa.
    fuel_ids = np.array(ref.ROAD_FUEL_IDS + ["F008"])
    # Diesel dominates litres; the 93/95 split varies inland vs coastal.
    grade_p = np.array([0.24, 0.19, 0.41, 0.14, 0.02])
    grade_p = grade_p / grade_p.sum()
    assert len(fuel_ids) == len(grade_p)
    base_price = {p.product_id: p.base_price_zar for p in ref.PRODUCTS}
    base_cost = {p.product_id: p.base_cost_zar for p in ref.PRODUCTS}
    site_lookup = ctx.site.set_index("site_id")

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        sites = c.weighted_sites(rng, ctx, n)
        prods = rng.choice(fuel_ids, n, p=grade_p)

        s = site_lookup.loc[sites]
        is_truck = (s["site_type"] == "Truck Stop").to_numpy()
        is_highway = s["on_national_route"].to_numpy()

        # Fill size: passenger cars cluster near 35-45 L, trucks far higher.
        litres = rng.gamma(4.2, 9.5, n)
        litres = np.where(is_truck, litres * rng.uniform(3.0, 6.5, n), litres)
        litres = np.where(is_highway & ~is_truck, litres * 1.18, litres)
        litres = litres.clip(4.0, 900.0)

        unit_price = np.zeros(n)
        for pid in fuel_ids:
            m = prods == pid
            if m.any():
                unit_price[m] = c.price_path(ts[m], base_price[pid], rng, int(m.sum()))

        gross = litres * unit_price
        cost_ratio = np.array([base_cost[p] / base_price[p] for p in prods])
        cogs = gross * cost_ratio * rng.normal(1.0, 0.012, n).clip(0.94, 1.06)

        payment = rng.choice(
            ["Card", "Cash", "Fleet Card", "Mobile App", "Voucher"], n,
            p=[0.46, 0.24, 0.18, 0.10, 0.02])
        loyalty = rng.random(n) < 0.34

        df = pd.DataFrame({
            "transaction_id": c.seq_ids("RF", offset, n),
            "transaction_ts": ts,
            "date_key": c.date_key(ts),
            "time_key": c.time_key(ts),
            "site_id": sites,
            "product_id": prods,
            "pump_number": rng.integers(1, 13, n).astype("int8"),
            "forecourt_lane": rng.integers(1, 13, n).astype("int8"),
            "shift_name": np.where(ts.dt.hour < 14, "Morning",
                           np.where(ts.dt.hour < 22, "Afternoon", "Night")),
            "litres": litres.round(3),
            "unit_price_zar": unit_price.round(3),
            "gross_sales_zar": gross.round(2),
            "cogs_zar": cogs.round(2),
            "gross_margin_zar": (gross - cogs).round(2),
            "payment_method": payment,
            "loyalty_flag": loyalty,
            "loyalty_member_id": np.where(
                loyalty, rng.choice(ctx.loyalty["loyalty_member_id"].to_numpy(), n), None),
            "is_fleet_sale": payment == "Fleet Card",
        })
        return c.add_audit_columns(df, "SRC01")

    return make_chunk


@fact("fact_shop_sales")
def shop_sales(rng, ctx, profile):
    shop_ids = np.array(ref.SHOP_IDS)
    price = {p.product_id: p.base_price_zar for p in ref.PRODUCTS}
    cost = {p.product_id: p.base_cost_zar for p in ref.PRODUCTS}
    shop_sites = ctx.site.loc[ctx.site["has_convenience"], "site_id"].to_numpy()
    if len(shop_sites) == 0:
        shop_sites = ctx.site_ids

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        prods = rng.choice(shop_ids, n,
                           p=_norm([0.20, 0.19, 0.14, 0.16, 0.05, 0.09, 0.12, 0.05]))
        qty = rng.choice([1, 2, 3, 4, 5], n, p=[0.58, 0.25, 0.10, 0.05, 0.02])
        unit = np.array([price[p] for p in prods]) * rng.normal(1.0, 0.09, n).clip(0.7, 1.4)
        unit_cost = np.array([cost[p] for p in prods]) * rng.normal(1.0, 0.05, n).clip(0.8, 1.25)
        gross = qty * unit
        cogs = qty * unit_cost
        df = pd.DataFrame({
            "shop_line_id": c.seq_ids("SH", offset, n),
            "basket_id": c.seq_ids("BSK", offset // 2, n, 12),
            "transaction_ts": ts,
            "date_key": c.date_key(ts),
            "time_key": c.time_key(ts),
            "site_id": rng.choice(shop_sites, n),
            "product_id": prods,
            "quantity": qty.astype("int16"),
            "unit_price_zar": unit.round(2),
            "gross_sales_zar": gross.round(2),
            "cogs_zar": cogs.round(2),
            "gross_margin_zar": (gross - cogs).round(2),
            "promotion_applied": rng.random(n) < 0.17,
            "payment_method": rng.choice(ref.PAYMENT_METHODS, n,
                                         p=[0.44, 0.31, 0.06, 0.11, 0.05, 0.03]),
        })
        return c.add_audit_columns(df, "SRC02")

    return make_chunk


@fact("fact_retail_fuel_payments")
def retail_fuel_payments(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        amount = rng.gamma(4.0, 190, n).clip(30, 40_000)
        method = rng.choice(ref.PAYMENT_METHODS, n, p=[0.46, 0.24, 0.16, 0.09, 0.03, 0.02])
        df = pd.DataFrame({
            "payment_id": c.seq_ids("PAY", offset, n),
            "transaction_id": c.seq_ids("RF", offset, n),
            "payment_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "payment_method": method,
            "amount_zar": amount.round(2),
            "authorisation_code": [f"AUTH{x:08d}" for x in rng.integers(1, 10**8, n)],
            "is_approved": rng.random(n) < 0.977,
            "settlement_days": np.where(method == "Account", 30,
                                np.where(method == "Voucher", 7, 1)).astype("int8"),
        })
        return c.add_audit_columns(df, "SRC01")

    return make_chunk


@fact("fact_shop_returns")
def shop_returns(rng, ctx, profile):
    shop_ids = np.array(ref.SHOP_IDS)

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n)
        qty = rng.choice([1, 2], n, p=[0.87, 0.13])
        value = qty * rng.uniform(10, 190, n)
        df = pd.DataFrame({
            "return_id": c.seq_ids("RET", offset, n),
            "return_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "product_id": rng.choice(shop_ids, n),
            "quantity_returned": qty.astype("int16"),
            "refund_value_zar": value.round(2),
            "reason_code": rng.choice(
                ["Damaged", "Expired", "Wrong Item", "Customer Change of Mind"], n),
            "approved_by_employee_id": rng.choice(ctx.employee["employee_id"].to_numpy(), n),
        })
        return c.add_audit_columns(df, "SRC02")

    return make_chunk


@fact("fact_forecourt_shift")
def forecourt_shift(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        shift = rng.choice(ref.SHIFTS, n)
        litres = rng.gamma(3.4, 2_600, n).clip(200, 120_000)
        df = pd.DataFrame({
            "forecourt_shift_id": c.seq_ids("FS", offset, n),
            "business_date": ts,
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "shift_name": shift,
            "supervisor_employee_id": rng.choice(ctx.employee["employee_id"].to_numpy(), n),
            "attendants_on_duty": rng.integers(1, 9, n).astype("int8"),
            "litres_dispensed": litres.round(1),
            "transaction_count": (litres / rng.uniform(38, 62, n)).astype("int32"),
            "cash_declared_zar": (litres * rng.uniform(4.5, 8.5, n)).round(2),
            "cash_variance_zar": rng.normal(0, 42, n).round(2),
            "pump_downtime_minutes": rng.gamma(1.1, 12, n).clip(0, 480).round(1),
        })
        return c.add_audit_columns(df, "SRC01")

    return make_chunk


@fact("fact_pump_meter_readings")
def pump_meter_readings(rng, ctx, profile):
    pump_ids = ctx.pump["pump_id"].to_numpy()
    pump_site = ctx.pump.set_index("pump_id")["site_id"]

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        pumps = rng.choice(pump_ids, n)
        totaliser = rng.uniform(50_000, 9_800_000, n)
        df = pd.DataFrame({
            "reading_id": c.seq_ids("PMR", offset, n),
            "reading_ts": ts,
            "date_key": c.date_key(ts),
            "pump_id": pumps,
            "site_id": pump_site.loc[pumps].to_numpy(),
            "product_id": rng.choice(ref.ROAD_FUEL_IDS, n),
            "totaliser_litres": totaliser.round(2),
            "litres_since_last_reading": rng.gamma(2.6, 260, n).clip(0, 26_000).round(2),
            "meter_drift_pct": rng.normal(0, 0.16, n).round(4),
            "calibration_due": rng.random(n) < 0.06,
        })
        return c.add_audit_columns(df, "SRC01")

    return make_chunk


@fact("fact_tank_dips")
def tank_dips(rng, ctx, profile):
    tank = ctx.tank
    tank_ids = tank["tank_id"].to_numpy()
    tank_idx = tank.set_index("tank_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        tks = rng.choice(tank_ids, n)
        t = tank_idx.loc[tks]
        cap = t["capacity_litres"].to_numpy()
        # Stock cycles between a reorder point and a full delivery.
        fill = rng.beta(2.4, 2.0, n)
        volume = cap * fill
        water = np.where(rng.random(n) < 0.04, rng.uniform(1, 45, n), 0.0)
        df = pd.DataFrame({
            "tank_dip_id": c.seq_ids("TD", offset, n),
            "dip_ts": ts,
            "date_key": c.date_key(ts),
            "tank_id": tks,
            "site_id": t["site_id"].to_numpy(),
            "product_id": t["product_id"].to_numpy(),
            "capacity_litres": cap,
            "volume_litres": volume.round(1),
            "ullage_litres": (cap - volume).round(1),
            "fill_pct": (fill * 100).round(2),
            "water_level_mm": water.round(1),
            "temperature_celsius": rng.normal(21, 5.5, n).round(1),
            "below_reorder_point": fill < 0.28,
            "reading_source": rng.choice(["Automatic Tank Gauge", "Manual Dip"], n,
                                         p=[0.86, 0.14]),
        })
        return c.add_audit_columns(df, "SRC03")

    return make_chunk


@fact("fact_price_changes")
def price_changes(rng, ctx, profile):
    base_price = {p.product_id: p.base_price_zar for p in ref.PRODUCTS}

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        prods = rng.choice(ref.ROAD_FUEL_IDS, n)
        old = np.array([base_price[p] for p in prods]) * rng.normal(1.0, 0.06, n)
        delta = rng.normal(0, 0.55, n)
        df = pd.DataFrame({
            "price_change_id": c.seq_ids("PC", offset, n),
            "effective_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "product_id": prods,
            "old_price_zar": old.round(3),
            "new_price_zar": (old + delta).round(3),
            "change_cents_per_litre": (delta * 100).round(1),
            "change_reason": rng.choice(
                ["Regulated Monthly Adjustment", "Zone Differential",
                 "Competitor Response", "Promotion"], n, p=[0.74, 0.12, 0.09, 0.05]),
            "approved_by_employee_id": rng.choice(ctx.employee["employee_id"].to_numpy(), n),
        })
        return c.add_audit_columns(df, "SRC07")

    return make_chunk


@fact("fact_promotions")
def promotions(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        uplift = rng.normal(0.11, 0.07, n)
        df = pd.DataFrame({
            "promotion_fact_id": c.seq_ids("PF", offset, n),
            "measurement_date": ts.dt.normalize(),
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "promotion_id": rng.choice(
                np.array([f"PRM{i:05d}" for i in range(1, 401)]), n),
            "baseline_units": rng.gamma(2.2, 120, n).round(0),
            "promoted_units": rng.gamma(2.2, 140, n).round(0),
            "uplift_pct": uplift.round(4),
            "discount_cost_zar": rng.gamma(2.0, 850, n).round(2),
            "incremental_margin_zar": rng.normal(1200, 900, n).round(2),
        })
        return c.add_audit_columns(df, "SRC02")

    return make_chunk


@fact("fact_site_daily_operations")
def site_daily_operations(rng, ctx, profile):
    site_lookup = ctx.site.set_index("site_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        sites = c.weighted_sites(rng, ctx, n)
        di = site_lookup.loc[sites, "demand_index"].to_numpy()
        litres = rng.gamma(5.0, 1_500, n) * di
        df = pd.DataFrame({
            "site_day_id": c.seq_ids("SDO", offset, n),
            "business_date": ts,
            "date_key": c.date_key(ts),
            "site_id": sites,
            "fuel_litres": litres.round(1),
            "fuel_revenue_zar": (litres * rng.uniform(22.0, 25.0, n)).round(2),
            "shop_revenue_zar": (litres * rng.uniform(0.9, 2.4, n)).round(2),
            "customer_count": (litres / rng.uniform(40, 58, n)).astype("int32"),
            "average_basket_zar": rng.normal(118, 34, n).clip(20, 700).round(2),
            "staff_hours": rng.normal(58, 16, n).clip(8, 220).round(1),
            "energy_kwh": rng.normal(410, 120, n).clip(30, 2400).round(1),
            "downtime_minutes": rng.gamma(1.0, 11, n).clip(0, 720).round(1),
            "weather_condition": rng.choice(ref.WEATHER_CONDITIONS, n,
                                            p=[0.46, 0.24, 0.14, 0.05, 0.06, 0.03, 0.02]),
        })
        return c.add_audit_columns(df, "SRC01")

    return make_chunk


def _norm(p):
    a = np.array(p, dtype=float)
    return a / a.sum()
