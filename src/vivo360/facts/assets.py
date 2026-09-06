"""Asset, maintenance and reliability facts.

`failure_propensity` on dim_asset drives work-order and failure rates so that
the predictive-maintenance model in ml/ has genuine signal to recover.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fact
from . import _common as c
from .. import reference as ref


@fact("fact_maintenance_work_orders")
def maintenance_work_orders(rng, ctx, profile):
    asset = ctx.asset
    asset_ids = asset["asset_id"].to_numpy()
    # Assets that are old and critical generate disproportionate work.
    w = asset["failure_propensity"].to_numpy(dtype=float)
    w = w / w.sum()
    asset_idx = asset.set_index("asset_id")

    def make_chunk(offset, n):
        raised = c.uniform_timestamps(rng, n)
        ids = rng.choice(asset_ids, n, p=w)
        a = asset_idx.loc[ids]
        crit = a["criticality"].to_numpy()

        # Whether a work order is a breakdown must depend on the asset's own
        # condition, not just on how often it appears. Without this the
        # breakdown rate is flat across age and the predictive-maintenance
        # model in ml/ has nothing to learn.
        prop = a["failure_propensity"].to_numpy(dtype=float)
        p_breakdown = np.clip(0.03 + 2.9 * prop, 0.02, 0.62)
        is_breakdown = rng.random(n) < p_breakdown
        planned = rng.choice(
            ["Preventive", "Corrective", "Predictive", "Statutory Inspection"],
            n, p=[0.39, 0.33, 0.12, 0.16])
        mtype = np.where(is_breakdown, "Breakdown", planned)
        # Breakdowns take longer and cost more than planned work.
        labour_h = np.where(is_breakdown,
                            rng.gamma(2.4, 3.6, n),
                            rng.gamma(1.8, 1.9, n)).clip(0.25, 90)
        parts = np.where(is_breakdown,
                         rng.gamma(2.0, 3_600, n),
                         rng.gamma(1.5, 1_100, n))
        response_h = np.where(
            crit == "Critical", rng.gamma(1.4, 1.6, n),
            np.where(crit == "High", rng.gamma(1.6, 3.2, n), rng.gamma(2.0, 9.0, n)))

        df = pd.DataFrame({
            "work_order_id": c.seq_ids("WO", offset, n),
            "raised_ts": raised,
            "date_key": c.date_key(raised),
            "asset_id": ids,
            "site_id": a["site_id"].to_numpy(),
            "asset_type": a["asset_type"].to_numpy(),
            "criticality": crit,
            "asset_age_years": a["age_years"].to_numpy(),
            "maintenance_type": mtype,
            "failure_mode": np.where(
                is_breakdown, rng.choice(ref.FAILURE_MODES, n), None),
            "priority": rng.choice(["Low", "Medium", "High", "Emergency"], n,
                                   p=[0.28, 0.42, 0.24, 0.06]),
            "response_hours": response_h.round(2),
            "labour_hours": labour_h.round(2),
            "labour_cost_zar": (labour_h * rng.normal(485, 90, n)).round(2),
            "parts_cost_zar": parts.round(2),
            "total_cost_zar": (labour_h * rng.normal(485, 90, n) + parts).round(2),
            "completed_ts": raised + pd.to_timedelta(
                (response_h + labour_h).round(2), unit="h"),
            "is_completed": rng.random(n) < 0.94,
            "is_breakdown": is_breakdown,
            "technician_employee_id": rng.choice(
                ctx.employee["employee_id"].to_numpy(), n),
            "sla_breached": response_h > np.where(crit == "Critical", 4, 24),
        })
        return c.add_audit_columns(df, "SRC12")

    return make_chunk


@fact("fact_asset_downtime")
def asset_downtime(rng, ctx, profile):
    asset = ctx.asset
    asset_ids = asset["asset_id"].to_numpy()
    w = asset["failure_propensity"].to_numpy(dtype=float)
    w = w / w.sum()
    asset_idx = asset.set_index("asset_id")

    def make_chunk(offset, n):
        start = c.uniform_timestamps(rng, n)
        ids = rng.choice(asset_ids, n, p=w)
        hours = rng.gamma(1.7, 5.4, n).clip(0.1, 400)
        planned = rng.random(n) < 0.42
        df = pd.DataFrame({
            "downtime_id": c.seq_ids("DT", offset, n),
            "downtime_start_ts": start,
            "downtime_end_ts": start + pd.to_timedelta(hours.round(2), unit="h"),
            "date_key": c.date_key(start),
            "asset_id": ids,
            "site_id": asset_idx.loc[ids, "site_id"].to_numpy(),
            "asset_type": asset_idx.loc[ids, "asset_type"].to_numpy(),
            "downtime_hours": hours.round(3),
            "is_planned": planned,
            "downtime_category": np.where(planned, "Planned Maintenance",
                                  rng.choice(["Breakdown", "Power Failure",
                                              "Safety Stop", "Awaiting Parts"], n)),
            "lost_volume_litres": np.where(planned, 0.0,
                                           hours * rng.gamma(2.0, 160, n)).round(1),
            "lost_revenue_zar": np.where(planned, 0.0,
                                         hours * rng.gamma(2.0, 3_400, n)).round(2),
        })
        return c.add_audit_columns(df, "SRC12")

    return make_chunk


@fact("fact_asset_inspections")
def asset_inspections(rng, ctx, profile):
    asset_idx = ctx.asset.set_index("asset_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        ids = rng.choice(ctx.asset_ids, n)
        passed = rng.random(n) < 0.88
        df = pd.DataFrame({
            "inspection_id": c.seq_ids("INS", offset, n),
            "inspection_ts": ts,
            "date_key": c.date_key(ts),
            "asset_id": ids,
            "site_id": asset_idx.loc[ids, "site_id"].to_numpy(),
            "inspection_type": rng.choice(
                ["Routine Visual", "Statutory", "Calibration",
                 "Leak Test", "Thermographic"], n,
                p=[0.44, 0.19, 0.16, 0.14, 0.07]),
            "inspector_employee_id": rng.choice(
                ctx.employee["employee_id"].to_numpy(), n),
            "result": np.where(passed, "Pass",
                       rng.choice(["Fail", "Conditional Pass"], n, p=[0.4, 0.6])),
            "defects_found": np.where(passed, rng.poisson(0.2, n),
                                      rng.poisson(2.4, n)).astype("int16"),
            "condition_score": rng.beta(6, 2, n).round(3) * 100,
            "next_due_date": ts + pd.to_timedelta(
                rng.choice([30, 90, 180, 365], n), unit="D"),
            "is_overdue": rng.random(n) < 0.09,
        })
        return c.add_audit_columns(df, "SRC12")

    return make_chunk


@fact("fact_asset_failures")
def asset_failures(rng, ctx, profile):
    asset = ctx.asset
    asset_ids = asset["asset_id"].to_numpy()
    w = asset["failure_propensity"].to_numpy(dtype=float)
    w = w / w.sum()
    asset_idx = asset.set_index("asset_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        ids = rng.choice(asset_ids, n, p=w)
        a = asset_idx.loc[ids]
        repair_h = rng.gamma(2.2, 4.1, n).clip(0.2, 220)
        df = pd.DataFrame({
            "failure_id": c.seq_ids("FL", offset, n),
            "failure_ts": ts,
            "date_key": c.date_key(ts),
            "asset_id": ids,
            "site_id": a["site_id"].to_numpy(),
            "asset_type": a["asset_type"].to_numpy(),
            "asset_age_years": a["age_years"].to_numpy(),
            "failure_mode": rng.choice(ref.FAILURE_MODES, n),
            "detection_method": rng.choice(
                ["Operator Report", "Telemetry Alert", "Inspection",
                 "Customer Complaint", "Predictive Model"], n,
                p=[0.36, 0.31, 0.16, 0.11, 0.06]),
            "time_to_repair_hours": repair_h.round(2),
            "repair_cost_zar": rng.gamma(2.1, 4_200, n).round(2),
            "is_repeat_failure": rng.random(n) < 0.17,
            "root_cause_identified": rng.random(n) < 0.74,
        })
        return c.add_audit_columns(df, "SRC12")

    return make_chunk


@fact("fact_spare_parts_usage")
def spare_parts_usage(rng, ctx, profile):
    parts = np.array([f"PART{i:05d}" for i in range(1, 1201)])

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        qty = rng.integers(1, 12, n)
        unit = rng.gamma(2.0, 480, n).clip(15, 90_000)
        df = pd.DataFrame({
            "parts_usage_id": c.seq_ids("SPU", offset, n),
            "usage_ts": ts,
            "date_key": c.date_key(ts),
            "work_order_id": c.seq_ids("WO", offset // 3, n, 12),
            "asset_id": rng.choice(ctx.asset_ids, n),
            "part_number": rng.choice(parts, n),
            "quantity_used": qty.astype("int16"),
            "unit_cost_zar": unit.round(2),
            "total_cost_zar": (qty * unit).round(2),
            "warehouse_id": np.array([f"WH{x:04d}" for x in rng.integers(1, 61, n)]),
            "was_stocked_out": rng.random(n) < 0.09,
            "lead_time_days": rng.gamma(1.8, 5.5, n).clip(0, 120).round(1),
        })
        return c.add_audit_columns(df, "SRC12")

    return make_chunk


@fact("fact_asset_meter_readings")
def asset_meter_readings(rng, ctx, profile):
    asset_idx = ctx.asset.set_index("asset_id")

    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        ids = rng.choice(ctx.asset_ids, n)
        # Vibration and temperature are the predictive-maintenance signals.
        prop = asset_idx.loc[ids, "failure_propensity"].to_numpy().astype(float)
        vibration = 1.8 + prop * 9.5 + rng.normal(0, 0.55, n)
        df = pd.DataFrame({
            "meter_reading_id": c.seq_ids("AMR", offset, n),
            "reading_ts": ts,
            "date_key": c.date_key(ts),
            "asset_id": ids,
            "site_id": asset_idx.loc[ids, "site_id"].to_numpy(),
            "running_hours": rng.uniform(0, 90_000, n).round(1),
            "cycle_count": rng.integers(0, 4_000_000, n),
            "vibration_mm_s": vibration.clip(0.1, 40).round(3),
            "temperature_celsius": (38 + prop * 60 + rng.normal(0, 4.5, n)).round(2),
            "pressure_bar": rng.normal(3.4, 0.7, n).clip(0.2, 9).round(3),
            "current_draw_amps": rng.normal(14.5, 3.8, n).clip(0.5, 60).round(2),
            "is_alarm": vibration > 9.5,
        })
        return c.add_audit_columns(df, "SRC12")

    return make_chunk
