"""Primary distribution, fleet and route facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fact
from . import _common as c
from .. import reference as ref


@fact("fact_deliveries")
def deliveries(rng, ctx, profile):
    route = ctx.route
    route_ids = route["route_id"].to_numpy()
    route_idx = route.set_index("route_id")
    veh_idx = ctx.vehicle.set_index("vehicle_id")

    def make_chunk(offset, n):
        planned = c.sample_timestamps(rng, n, hourly=False)
        routes = rng.choice(route_ids, n)
        r = route_idx.loc[routes]
        distance = r["planned_distance_km"].to_numpy() * rng.normal(1.0, 0.07, n)
        drops = r["drop_count"].to_numpy()

        vehicles = rng.choice(ctx.vehicle_ids, n)
        cap = veh_idx.loc[vehicles, "capacity_litres"].to_numpy().astype(float)
        delivered = cap * rng.uniform(0.62, 1.0, n)

        # Delay is driven by distance, drop count and a congestion tail.
        base_delay = rng.normal(6, 18, n) + distance * 0.035 + drops * 3.1
        congestion = np.where(rng.random(n) < 0.14, rng.gamma(2.3, 62, n), 0.0)
        delay = base_delay + congestion
        actual = planned + pd.to_timedelta(delay.round(0), unit="m")

        df = pd.DataFrame({
            "delivery_id": c.seq_ids("DL", offset, n),
            "planned_arrival_ts": planned,
            "actual_arrival_ts": actual,
            "date_key": c.date_key(planned),
            "route_id": routes,
            "origin_terminal_id": r["origin_terminal_id"].to_numpy(),
            "destination_site_id": c.weighted_sites(rng, ctx, n),
            "vehicle_id": vehicles,
            "driver_id": rng.choice(ctx.driver["driver_id"].to_numpy(), n),
            "carrier_id": veh_idx.loc[vehicles, "carrier_id"].to_numpy(),
            "product_id": rng.choice(ref.ROAD_FUEL_IDS, n),
            "planned_litres": cap.round(0),
            "delivered_litres": delivered.round(2),
            "fill_rate_pct": (delivered / cap * 100).round(2),
            "distance_km": distance.round(1),
            "drop_count": drops.astype("int8"),
            "delay_minutes": delay.round(0).astype("int32"),
            "is_late": delay > 60,
            "otif_flag": (delay <= 60) & (delivered >= cap * 0.98),
            "delivery_status": rng.choice(ref.DELIVERY_STATUSES, n,
                                          p=[0.005, 0.01, 0.015, 0.90, 0.055, 0.015]),
            "reason_code": rng.choice(ref.REASON_CODES, n, p=_reason_p()),
        })
        return c.add_audit_columns(df, "SRC04")

    return make_chunk


@fact("fact_delivery_events")
def delivery_events(rng, ctx, profile):
    events = np.array(["Dispatched", "Departed Terminal", "In Transit",
                       "Arrived Site", "Discharge Started", "Discharge Complete",
                       "Departed Site", "Exception Raised"])

    def make_chunk(offset, n):
        ts = c.sample_timestamps(rng, n, hourly=False)
        df = pd.DataFrame({
            "delivery_event_id": c.seq_ids("DE", offset, n),
            "event_ts": ts,
            "date_key": c.date_key(ts),
            "delivery_id": c.seq_ids("DL", offset // 4, n, 12),
            "event_type": rng.choice(events, n,
                                     p=[0.13, 0.13, 0.20, 0.13, 0.13, 0.12, 0.12, 0.04]),
            "vehicle_id": rng.choice(ctx.vehicle_ids, n),
            "latitude": rng.uniform(-34.6, -22.3, n).round(5),
            "longitude": rng.uniform(16.5, 32.9, n).round(5),
            "speed_kph": rng.normal(58, 24, n).clip(0, 122).round(1),
            "odometer_km": rng.uniform(20_000, 1_400_000, n).round(1),
            "geofence_name": rng.choice(
                ["Terminal Zone", "Customer Zone", "Highway", "Urban", "Rest Stop"], n),
            "is_exception": rng.random(n) < 0.04,
        })
        return c.add_audit_columns(df, "SRC04")

    return make_chunk


@fact("fact_vehicle_trips")
def vehicle_trips(rng, ctx, profile):
    veh_idx = ctx.vehicle.set_index("vehicle_id")

    def make_chunk(offset, n):
        start = c.sample_timestamps(rng, n, hourly=False)
        distance = rng.gamma(2.4, 108, n).clip(3, 1500)
        avg_speed = rng.normal(56, 11, n).clip(22, 92)
        hours = distance / avg_speed
        vehicles = rng.choice(ctx.vehicle_ids, n)
        # Heavier vehicles burn more; consumption also rises with harsh driving.
        cap = veh_idx.loc[vehicles, "capacity_litres"].to_numpy().astype(float)
        l_per_100 = 26 + cap / 4200 + rng.normal(0, 3.1, n)
        fuel = distance / 100 * l_per_100
        df = pd.DataFrame({
            "trip_id": c.seq_ids("TRP", offset, n),
            "trip_start_ts": start,
            "trip_end_ts": start + pd.to_timedelta(hours.round(2), unit="h"),
            "date_key": c.date_key(start),
            "vehicle_id": vehicles,
            "driver_id": rng.choice(ctx.driver["driver_id"].to_numpy(), n),
            "route_id": rng.choice(ctx.route["route_id"].to_numpy(), n),
            "distance_km": distance.round(1),
            "duration_hours": hours.round(3),
            "average_speed_kph": avg_speed.round(1),
            "fuel_consumed_litres": fuel.round(2),
            "litres_per_100km": l_per_100.round(2),
            "idle_minutes": rng.gamma(1.9, 14, n).clip(0, 420).round(1),
            "harsh_braking_events": rng.poisson(1.4, n).astype("int16"),
            "harsh_acceleration_events": rng.poisson(1.1, n).astype("int16"),
            "speeding_events": rng.poisson(0.9, n).astype("int16"),
        })
        return c.add_audit_columns(df, "SRC04")

    return make_chunk


@fact("fact_route_performance")
def route_performance(rng, ctx, profile):
    route_idx = ctx.route.set_index("route_id")
    route_ids = ctx.route["route_id"].to_numpy()

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        routes = rng.choice(route_ids, n)
        r = route_idx.loc[routes]
        planned_km = r["planned_distance_km"].to_numpy()
        actual_km = planned_km * rng.normal(1.04, 0.09, n)
        planned_h = r["planned_duration_hours"].to_numpy()
        actual_h = planned_h * rng.normal(1.07, 0.16, n)
        df = pd.DataFrame({
            "route_performance_id": c.seq_ids("RP", offset, n),
            "business_date": ts,
            "date_key": c.date_key(ts),
            "route_id": routes,
            "planned_distance_km": planned_km.round(1),
            "actual_distance_km": actual_km.round(1),
            "distance_variance_pct": ((actual_km / planned_km - 1) * 100).round(2),
            "planned_duration_hours": planned_h.round(2),
            "actual_duration_hours": actual_h.round(2),
            "drops_planned": r["drop_count"].to_numpy().astype("int8"),
            "drops_completed": np.maximum(
                1, r["drop_count"].to_numpy() - rng.binomial(1, 0.06, n)).astype("int8"),
            "cost_per_km_zar": rng.normal(21.5, 4.2, n).clip(8, 60).round(2),
            "utilisation_pct": rng.beta(6, 2.2, n).round(4) * 100,
        })
        return c.add_audit_columns(df, "SRC04")

    return make_chunk


@fact("fact_fleet_costs")
def fleet_costs(rng, ctx, profile):
    cost_types = np.array(["Fuel", "Tyres", "Maintenance", "Insurance",
                           "Driver Wages", "Licensing", "Tolls", "Depreciation"])

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n).dt.normalize()
        ct = rng.choice(cost_types, n, p=[0.34, 0.07, 0.14, 0.07, 0.20, 0.03, 0.06, 0.09])
        scale = pd.Series(ct).map({
            "Fuel": 24_000, "Tyres": 6_500, "Maintenance": 9_800,
            "Insurance": 5_200, "Driver Wages": 18_500, "Licensing": 1_400,
            "Tolls": 3_100, "Depreciation": 12_600,
        }).to_numpy()
        amount = scale * rng.lognormal(0, 0.42, n)
        df = pd.DataFrame({
            "fleet_cost_id": c.seq_ids("FC", offset, n),
            "cost_date": ts,
            "date_key": c.date_key(ts),
            "vehicle_id": rng.choice(ctx.vehicle_ids, n),
            "carrier_id": rng.choice(ctx.vehicle["carrier_id"].to_numpy(), n),
            "cost_type": ct,
            "amount_zar": amount.round(2),
            "kilometres_in_period": rng.gamma(3.0, 2_100, n).clip(80, 40_000).round(1),
            "cost_centre_code": rng.choice(
                ctx.cost_centre["cost_centre_code"].to_numpy(), n),
            "is_accrual": rng.random(n) < 0.12,
        })
        return c.add_audit_columns(df, "SRC08")

    return make_chunk


def _reason_p():
    p = np.array([0.05, 0.08, 0.14, 0.04, 0.03, 0.02, 0.05, 0.03, 0.56])
    return p / p.sum()
