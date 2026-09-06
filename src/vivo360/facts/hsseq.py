"""Health, safety, security, environment and quality facts."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import fact
from . import _common as c
from .. import reference as ref


@fact("fact_hsseq_incidents")
def hsseq_incidents(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        severity = rng.choice(ref.INCIDENT_SEVERITIES, n,
                              p=[0.44, 0.31, 0.16, 0.07, 0.02])
        rank = pd.Series(severity).map(
            {"Near Miss": 1, "Minor": 2, "Moderate": 3,
             "Serious": 4, "Major": 5}).to_numpy()
        # Lost time and cost scale sharply with severity.
        lost_days = np.where(rank >= 3, rng.gamma(1.6, rank * 2.2), 0.0)
        cost = rng.gamma(1.8, np.power(6.5, rank) * 9)
        df = pd.DataFrame({
            "incident_id": c.seq_ids("HSE", offset, n),
            "incident_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "incident_type": rng.choice(ref.INCIDENT_TYPES, n,
                                        p=[0.21, 0.17, 0.14, 0.05, 0.08,
                                           0.15, 0.06, 0.09, 0.05]),
            "severity": severity,
            "severity_rank": rank.astype("int8"),
            "is_lost_time_injury": (rank >= 3) & (lost_days > 0),
            "lost_days": lost_days.round(1),
            "people_affected": rng.poisson(0.6, n).astype("int16"),
            "estimated_cost_zar": cost.round(2),
            "is_reportable": rank >= 3,
            "root_cause_category": rng.choice(
                ["Human Factors", "Equipment", "Procedure", "Environment",
                 "Contractor", "Design"], n,
                p=[0.31, 0.22, 0.19, 0.11, 0.11, 0.06]),
            "corrective_actions_raised": rng.poisson(1.9, n).astype("int16"),
            "corrective_actions_closed": rng.poisson(1.4, n).astype("int16"),
            "investigation_days": rng.gamma(2.0, 5.5, n).clip(0, 180).round(1),
            "reported_by_employee_id": rng.choice(
                ctx.employee["employee_id"].to_numpy(), n),
        })
        return c.add_audit_columns(df, "SRC13")

    return make_chunk


@fact("fact_near_misses")
def near_misses(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        df = pd.DataFrame({
            "near_miss_id": c.seq_ids("NM", offset, n),
            "reported_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "hazard_type": rng.choice(
                ["Spill Risk", "Slip Hazard", "Vehicle Movement",
                 "Electrical", "Working at Height", "Hot Work",
                 "Housekeeping", "Security"], n),
            "potential_severity": rng.choice(ref.INCIDENT_SEVERITIES, n,
                                             p=[0.10, 0.28, 0.34, 0.21, 0.07]),
            "immediate_action_taken": rng.random(n) < 0.87,
            "days_to_close": rng.gamma(1.8, 4.5, n).clip(0, 150).round(1),
            "reported_by_employee_id": rng.choice(
                ctx.employee["employee_id"].to_numpy(), n),
            "is_repeat_hazard": rng.random(n) < 0.21,
        })
        return c.add_audit_columns(df, "SRC13")

    return make_chunk


@fact("fact_environmental_events")
def environmental_events(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        volume = rng.gamma(1.4, 42, n).clip(0.1, 9_000)
        df = pd.DataFrame({
            "environmental_event_id": c.seq_ids("ENV", offset, n),
            "event_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": rng.choice(ctx.site_ids, n),
            "terminal_id": np.where(rng.random(n) < 0.2,
                                    rng.choice(ctx.terminal_ids, n), None),
            "event_type": rng.choice(
                ["Fuel Spill", "Oil Leak", "Groundwater Contamination",
                 "Air Emission Exceedance", "Waste Non-Compliance",
                 "Noise Complaint"], n,
                p=[0.34, 0.24, 0.10, 0.12, 0.14, 0.06]),
            "volume_released_litres": volume.round(2),
            "contained_flag": rng.random(n) < 0.88,
            "soil_affected_m2": rng.gamma(1.5, 18, n).clip(0, 4_000).round(1),
            "remediation_cost_zar": rng.gamma(1.9, 26_000, n).round(2),
            "regulator_notified": rng.random(n) < 0.31,
            "days_to_remediate": rng.gamma(2.2, 14, n).clip(0, 700).round(1),
        })
        return c.add_audit_columns(df, "SRC13")

    return make_chunk


@fact("fact_safety_observations")
def safety_observations(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        df = pd.DataFrame({
            "observation_id": c.seq_ids("OBS", offset, n),
            "observation_ts": ts,
            "date_key": c.date_key(ts),
            "site_id": c.weighted_sites(rng, ctx, n),
            "observer_employee_id": rng.choice(
                ctx.employee["employee_id"].to_numpy(), n),
            "observation_type": rng.choice(["Safe Act", "Unsafe Act",
                                            "Safe Condition", "Unsafe Condition"],
                                           n, p=[0.41, 0.19, 0.28, 0.12]),
            "category": rng.choice(
                ["PPE", "Housekeeping", "Vehicle Safety", "Fire Safety",
                 "Permit Compliance", "Manual Handling"], n),
            "is_positive": rng.random(n) < 0.69,
            "action_required": rng.random(n) < 0.28,
            "closed_flag": rng.random(n) < 0.83,
        })
        return c.add_audit_columns(df, "SRC13")

    return make_chunk


@fact("fact_training_compliance")
def training_compliance(rng, ctx, profile):
    courses = np.array(["Fire Safety", "Hazmat Handling", "Defensive Driving",
                        "First Aid", "Permit to Work", "Environmental Awareness",
                        "Forecourt Operations", "Working at Height"])

    def make_chunk(offset, n):
        completed = c.uniform_timestamps(rng, n).dt.normalize()
        valid_days = rng.choice([365, 730, 1095], n)
        expiry = completed + pd.to_timedelta(valid_days, unit="D")
        df = pd.DataFrame({
            "training_record_id": c.seq_ids("TRN", offset, n),
            "completed_date": completed,
            "date_key": c.date_key(completed),
            "employee_id": rng.choice(ctx.employee["employee_id"].to_numpy(), n),
            "site_id": rng.choice(ctx.site_ids, n),
            "course_name": rng.choice(courses, n),
            "result": rng.choice(["Pass", "Fail", "Refresher Required"], n,
                                 p=[0.89, 0.05, 0.06]),
            "score_pct": rng.beta(7, 2, n).round(3) * 100,
            "expiry_date": expiry,
            "is_expired": expiry < pd.Timestamp("2026-08-31"),
            "is_mandatory": rng.random(n) < 0.72,
            "training_hours": rng.choice([2, 4, 8, 16], n, p=[0.3, 0.35, 0.25, 0.1]),
        })
        return c.add_audit_columns(df, "SRC13")

    return make_chunk


@fact("fact_permit_to_work")
def permit_to_work(rng, ctx, profile):
    def make_chunk(offset, n):
        issued = c.uniform_timestamps(rng, n)
        hours = rng.gamma(2.0, 4.5, n).clip(0.5, 72)
        df = pd.DataFrame({
            "permit_id": c.seq_ids("PTW", offset, n),
            "issued_ts": issued,
            "date_key": c.date_key(issued),
            "site_id": rng.choice(ctx.site_ids, n),
            "permit_type": rng.choice(
                ["Hot Work", "Confined Space", "Working at Height",
                 "Excavation", "Electrical Isolation", "General"], n,
                p=[0.21, 0.09, 0.16, 0.11, 0.18, 0.25]),
            "contractor_flag": rng.random(n) < 0.54,
            "issued_by_employee_id": rng.choice(
                ctx.employee["employee_id"].to_numpy(), n),
            "planned_duration_hours": hours.round(2),
            "closed_ts": issued + pd.to_timedelta(hours.round(2), unit="h"),
            "isolations_required": rng.poisson(1.1, n).astype("int16"),
            "gas_test_performed": rng.random(n) < 0.42,
            "closed_correctly": rng.random(n) < 0.93,
        })
        return c.add_audit_columns(df, "SRC13")

    return make_chunk


@fact("fact_vehicle_safety_events")
def vehicle_safety_events(rng, ctx, profile):
    def make_chunk(offset, n):
        ts = c.uniform_timestamps(rng, n)
        severity = rng.choice(["Information", "Warning", "Critical"], n,
                              p=[0.56, 0.36, 0.08])
        df = pd.DataFrame({
            "vehicle_safety_event_id": c.seq_ids("VSE", offset, n),
            "event_ts": ts,
            "date_key": c.date_key(ts),
            "vehicle_id": rng.choice(ctx.vehicle_ids, n),
            "driver_id": rng.choice(ctx.driver["driver_id"].to_numpy(), n),
            "event_type": rng.choice(
                ["Harsh Braking", "Harsh Acceleration", "Over Speed",
                 "Fatigue Alert", "Lane Departure", "Seatbelt Unfastened",
                 "Excessive Idling"], n,
                p=[0.24, 0.18, 0.22, 0.08, 0.11, 0.07, 0.10]),
            "severity": severity,
            "speed_kph": rng.normal(72, 22, n).clip(0, 135).round(1),
            "speed_limit_kph": rng.choice([60, 80, 100, 120], n),
            "g_force": rng.gamma(2.0, 0.18, n).clip(0.05, 2.4).round(3),
            "latitude": rng.uniform(-34.6, -22.3, n).round(5),
            "longitude": rng.uniform(16.5, 32.9, n).round(5),
            "resulted_in_incident": (severity == "Critical") & (rng.random(n) < 0.14),
        })
        return c.add_audit_columns(df, "SRC04")

    return make_chunk
