"""EV charging, solar generation and site energy facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import reference as ref
from . import _common as c
from . import fact


@fact("fact_ev_charging_sessions")
def ev_charging_sessions(rng, ctx, profile):
    chargers = ctx.ev_charger
    charger_ids = chargers["ev_charger_id"].to_numpy()
    charger_idx = chargers.set_index("ev_charger_id")

    def make_chunk(offset, n):
        start = c.sample_timestamps(rng, n)
        ids = rng.choice(charger_ids, n)
        cg = charger_idx.loc[ids]
        rated = cg["rated_power_kw"].to_numpy().astype(float)

        # Energy delivered depends on charger rating and dwell time; AC units
        # are slow and used for long dwells, DC units for short top-ups.
        is_dc = rated >= 60
        minutes = np.where(is_dc,
                           rng.gamma(2.4, 12, n).clip(4, 120),
                           rng.gamma(2.8, 55, n).clip(20, 600))
        avg_power = rated * rng.uniform(0.45, 0.92, n)
        kwh = avg_power * (minutes / 60.0)
        tariff = np.where(is_dc, rng.normal(7.6, 0.5, n), rng.normal(5.4, 0.4, n))
        revenue = kwh * tariff
        grid_cost = kwh * rng.normal(2.9, 0.35, n)

        df = pd.DataFrame({
            "ev_session_id": c.seq_ids("EVS", offset, n),
            "session_start_ts": start,
            "session_end_ts": start + pd.to_timedelta(minutes.round(0), unit="m"),
            "date_key": c.date_key(start),
            "time_key": c.time_key(start),
            "ev_charger_id": ids,
            "site_id": cg["site_id"].to_numpy(),
            "connector_type": cg["connector_type"].to_numpy(),
            "rated_power_kw": rated,
            "duration_minutes": minutes.round(1),
            "energy_kwh": kwh.round(3),
            "average_power_kw": avg_power.round(2),
            "tariff_zar_per_kwh": tariff.round(3),
            "revenue_zar": revenue.round(2),
            "grid_cost_zar": grid_cost.round(2),
            "gross_margin_zar": (revenue - grid_cost).round(2),
            "start_soc_pct": rng.uniform(5, 62, n).round(1),
            "end_soc_pct": rng.uniform(63, 100, n).round(1),
            "payment_method": rng.choice(["Mobile App", "Card", "RFID Tag"], n,
                                         p=[0.58, 0.29, 0.13]),
            "session_ended_by": rng.choice(
                ["User", "Full Charge", "Fault", "Timeout"], n,
                p=[0.52, 0.39, 0.05, 0.04]),
        })
        return c.add_audit_columns(df, "SRC05")

    return make_chunk


@fact("fact_ev_charger_status")
def ev_charger_status(rng, ctx, profile):
    chargers = ctx.ev_charger
    charger_ids = chargers["ev_charger_id"].to_numpy()
    charger_idx = chargers.set_index("ev_charger_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        ids = rng.choice(charger_ids, n)
        status = rng.choice(
            ["Available", "Charging", "Preparing", "Finishing", "Faulted",
             "Unavailable"], n, p=[0.46, 0.31, 0.06, 0.05, 0.045, 0.075])
        df = pd.DataFrame({
            "charger_status_id": c.seq_ids("EVST", offset, n),
            "status_ts": ts,
            "date_key": c.date_key(ts),
            "ev_charger_id": ids,
            "site_id": charger_idx.loc[ids, "site_id"].to_numpy(),
            "status": status,
            "is_available": status == "Available",
            "is_faulted": status == "Faulted",
            "error_code": np.where(status == "Faulted",
                                   rng.choice(["EVSE-101", "EVSE-204", "EVSE-311",
                                               "EVSE-450"], n), None),
            "temperature_celsius": rng.normal(34, 9, n).round(1),
            "firmware_version": rng.choice(["1.8.4", "2.0.1", "2.1.0"], n),
        })
        return c.add_audit_columns(df, "SRC05")

    return make_chunk


@fact("fact_solar_generation")
def solar_generation(rng, ctx, profile):
    solar = ctx.solar_asset
    asset_ids = solar["solar_asset_id"].to_numpy()
    solar_idx = solar.set_index("solar_asset_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        ids = rng.choice(asset_ids, n)
        s = solar_idx.loc[ids]
        kwp = s["installed_kwp"].to_numpy().astype(float)

        hour = ts.dt.hour.to_numpy()
        month = ts.dt.month.to_numpy()
        # A daylight curve peaking at solar noon, zero at night.
        daylight = np.clip(np.sin((hour - 6.0) / 12.0 * np.pi), 0, None)
        # Southern-hemisphere seasonality: summer months generate more.
        seasonal = 0.86 + 0.20 * np.cos((month - 1) / 12.0 * 2 * np.pi)
        cloud = np.where(rng.random(n) < 0.28, rng.uniform(0.15, 0.75, n), 1.0)
        soiling = rng.uniform(0.93, 1.0, n)

        kwh = kwp * daylight * seasonal * cloud * soiling * 0.25
        capacity_factor = np.where(kwp > 0, kwh / (kwp * 0.25), 0.0)

        df = pd.DataFrame({
            "solar_reading_id": c.seq_ids("SG", offset, n),
            "reading_ts": ts,
            "date_key": c.date_key(ts),
            "time_key": c.time_key(ts),
            "solar_asset_id": ids,
            "site_id": s["site_id"].to_numpy(),
            "installed_kwp": kwp,
            "interval_minutes": 15,
            "energy_kwh": kwh.round(4),
            "irradiance_w_m2": (daylight * seasonal * cloud * 1000).round(1),
            "panel_temperature_celsius": (
                18 + daylight * 34 + rng.normal(0, 3.5, n)).round(1),
            "inverter_efficiency_pct": rng.normal(96.4, 1.4, n).clip(85, 99.4).round(2),
            "capacity_factor": capacity_factor.round(4),
            "is_daylight": daylight > 0,
            "co2_avoided_kg": (kwh * 0.95).round(3),
        })
        return c.add_audit_columns(df, "SRC06")

    return make_chunk


@fact("fact_site_energy_consumption")
def site_energy_consumption(rng, ctx, profile):
    site_idx = ctx.site.set_index("site_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        sites = c.weighted_sites(rng, ctx, n)
        di = site_idx.loc[sites, "demand_index"].to_numpy()
        hour = ts.dt.hour.to_numpy()
        # Forecourt load: canopy lighting overnight, refrigeration all day.
        load = (14 + 9 * np.sin((hour - 8) / 24 * 2 * np.pi) + 6 * (hour >= 18)) * di
        kwh = np.maximum(load * rng.normal(1.0, 0.14, n), 0.4)
        df = pd.DataFrame({
            "energy_consumption_id": c.seq_ids("SEC", offset, n),
            "reading_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": sites,
            "energy_source": rng.choice(ref.ENERGY_SOURCES, n,
                                        p=[0.71, 0.19, 0.07, 0.03]),
            "consumption_kwh": kwh.round(3),
            "peak_demand_kva": (kwh * rng.uniform(1.1, 1.9, n)).round(2),
            "power_factor": rng.normal(0.94, 0.03, n).clip(0.75, 1.0).round(3),
            "tariff_period": np.where(np.isin(hour, [7, 8, 9, 18, 19, 20]), "Peak",
                              np.where(np.isin(hour, range(10, 18)), "Standard", "Off Peak")),
            "cost_zar": (kwh * rng.normal(2.65, 0.4, n)).round(2),
        })
        return c.add_audit_columns(df, "SRC06")

    return make_chunk


@fact("fact_grid_import_export")
def grid_import_export(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        hour = ts.dt.hour.to_numpy()
        solar_out = np.clip(np.sin((hour - 6.0) / 12.0 * np.pi), 0, None) * rng.uniform(0, 46, n)
        demand = 16 + 8 * np.sin((hour - 8) / 24 * 2 * np.pi) + rng.normal(0, 3, n)
        net = demand - solar_out
        df = pd.DataFrame({
            "grid_flow_id": c.seq_ids("GRD", offset, n),
            "reading_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": rng.choice(ctx.site_ids, n),
            "import_kwh": np.maximum(net, 0).round(3),
            "export_kwh": np.maximum(-net, 0).round(3),
            "net_kwh": net.round(3),
            "self_consumption_pct": np.clip(
                (solar_out / np.maximum(demand, 0.1)) * 100, 0, 100).round(2),
            "load_shedding_stage": rng.choice([0, 1, 2, 3, 4, 6], n,
                                              p=[0.72, 0.09, 0.08, 0.06, 0.035, 0.015]),
            "backup_generator_running": rng.random(n) < 0.11,
        })
        return c.add_audit_columns(df, "SRC06")

    return make_chunk


@fact("fact_energy_costs")
def energy_costs(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        kwh = rng.gamma(3.2, 3_600, n).clip(200, 120_000)
        rate = rng.normal(2.72, 0.36, n).clip(1.4, 5.2)
        df = pd.DataFrame({
            "energy_cost_id": c.seq_ids("ECS", offset, n),
            "billing_period_start": ts,
            "date_key": c.date_key(ts),
            "site_id": rng.choice(ctx.site_ids, n),
            "energy_source": rng.choice(ref.ENERGY_SOURCES, n,
                                        p=[0.74, 0.16, 0.07, 0.03]),
            "consumption_kwh": kwh.round(1),
            "unit_rate_zar_per_kwh": rate.round(4),
            "demand_charge_zar": rng.gamma(2.0, 3_100, n).round(2),
            "energy_charge_zar": (kwh * rate).round(2),
            "total_cost_zar": (kwh * rate + rng.gamma(2.0, 3_100, n)).round(2),
            "carbon_kg": (kwh * 0.95).round(1),
            "cost_centre_code": rng.choice(
                ctx.cost_centre["cost_centre_code"].to_numpy(), n),
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk
