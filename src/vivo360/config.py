"""Build configuration: scales, date windows, and the fact row-count plan.

All volumes are synthetic. The ``portfolio`` profile is the contractual default
and must exceed 15,000,000 fact rows (enforced by tests/test_row_counts.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# --------------------------------------------------------------------------
# Time window
# --------------------------------------------------------------------------
DATE_START = date(2024, 1, 1)
DATE_END = date(2026, 8, 31)

DEFAULT_SEED = 3602026


# --------------------------------------------------------------------------
# Scale profiles
# --------------------------------------------------------------------------
# dev        - fast local loop, seconds
# test       - CI gate, about a minute
# portfolio  - contractual default, > 15M fact rows
# enterprise - stress profile, > 100M fact rows


@dataclass(frozen=True)
class ScaleProfile:
    """Dimension cardinalities and fact volumes for one build profile."""

    name: str
    sites_total: int
    sites_za: int
    customers: int
    suppliers: int
    terminals: int
    depots: int
    vehicles: int
    drivers: int
    employees: int
    assets: int
    tanks: int
    pumps: int
    loyalty_members: int
    digital_users: int
    ev_chargers: int
    solar_assets: int
    contracts: int
    routes: int
    facts: dict = field(default_factory=dict)
    secondary_scale: float = 1.0


DEV = ScaleProfile(
    name="dev",
    sites_total=220, sites_za=80, customers=1_500, suppliers=120, terminals=40,
    depots=25, vehicles=250, drivers=300, employees=800, assets=1_000,
    tanks=600, pumps=900, loyalty_members=5_000, digital_users=4_000,
    ev_chargers=120, solar_assets=90, contracts=900, routes=200,
    facts={
        "fact_retail_fuel_sales": 15_000, "fact_shop_sales": 10_000,
        "fact_commercial_orders": 3_000, "fact_inventory_snapshot": 5_000,
        "fact_deliveries": 2_500, "fact_procurement_receipts": 1_500,
        "fact_aviation_sales": 600, "fact_marine_sales": 400,
        "fact_lpg_sales": 1_500, "fact_lubricant_sales": 1_500,
        "fact_loyalty_transactions": 6_000, "fact_digital_events": 7_000,
        "fact_ev_charging_sessions": 700, "fact_solar_generation": 2_500,
        "fact_maintenance_work_orders": 900, "fact_hsseq_incidents": 150,
    },
    secondary_scale=0.02,
)

TEST = ScaleProfile(
    name="test",
    sites_total=600, sites_za=250, customers=6_000, suppliers=400, terminals=60,
    depots=40, vehicles=900, drivers=1_100, employees=3_000, assets=5_000,
    tanks=2_500, pumps=4_000, loyalty_members=30_000, digital_users=25_000,
    ev_chargers=400, solar_assets=300, contracts=3_500, routes=600,
    facts={
        "fact_retail_fuel_sales": 200_000, "fact_shop_sales": 120_000,
        "fact_commercial_orders": 25_000, "fact_inventory_snapshot": 50_000,
        "fact_deliveries": 15_000, "fact_procurement_receipts": 10_000,
        "fact_aviation_sales": 5_000, "fact_marine_sales": 4_000,
        "fact_lpg_sales": 16_000, "fact_lubricant_sales": 14_000,
        "fact_loyalty_transactions": 80_000, "fact_digital_events": 60_000,
        "fact_ev_charging_sessions": 6_000, "fact_solar_generation": 26_000,
        "fact_maintenance_work_orders": 4_000, "fact_hsseq_incidents": 800,
    },
    secondary_scale=0.06,
)

PORTFOLIO = ScaleProfile(
    name="portfolio",
    sites_total=4_200, sites_za=1_050, customers=150_000, suppliers=3_000,
    terminals=180, depots=120, vehicles=15_000, drivers=18_000,
    employees=45_000, assets=50_000, tanks=21_000, pumps=38_000,
    loyalty_members=2_400_000, digital_users=1_800_000, ev_chargers=2_600,
    solar_assets=1_900, contracts=40_000, routes=4_000,
    facts={
        "fact_retail_fuel_sales": 5_000_000, "fact_shop_sales": 3_000_000,
        "fact_commercial_orders": 550_000, "fact_inventory_snapshot": 1_200_000,
        "fact_deliveries": 300_000, "fact_procurement_receipts": 250_000,
        "fact_aviation_sales": 120_000, "fact_marine_sales": 90_000,
        "fact_lpg_sales": 400_000, "fact_lubricant_sales": 350_000,
        "fact_loyalty_transactions": 2_000_000, "fact_digital_events": 1_500_000,
        "fact_ev_charging_sessions": 150_000, "fact_solar_generation": 650_000,
        "fact_maintenance_work_orders": 80_000, "fact_hsseq_incidents": 15_000,
    },
    secondary_scale=1.0,
)

ENTERPRISE = ScaleProfile(
    name="enterprise",
    sites_total=8_000, sites_za=1_800, customers=600_000, suppliers=8_000,
    terminals=300, depots=220, vehicles=40_000, drivers=48_000,
    employees=120_000, assets=120_000, tanks=48_000, pumps=90_000,
    loyalty_members=9_000_000, digital_users=7_000_000, ev_chargers=9_000,
    solar_assets=6_500, contracts=140_000, routes=12_000,
    facts={
        "fact_retail_fuel_sales": 35_000_000, "fact_shop_sales": 20_000_000,
        "fact_commercial_orders": 5_000_000, "fact_inventory_snapshot": 8_000_000,
        "fact_deliveries": 2_000_000, "fact_procurement_receipts": 1_500_000,
        "fact_aviation_sales": 800_000, "fact_marine_sales": 600_000,
        "fact_lpg_sales": 3_000_000, "fact_lubricant_sales": 2_500_000,
        "fact_loyalty_transactions": 15_000_000, "fact_digital_events": 12_000_000,
        "fact_ev_charging_sessions": 1_500_000, "fact_solar_generation": 5_000_000,
        "fact_maintenance_work_orders": 600_000, "fact_hsseq_incidents": 120_000,
    },
    secondary_scale=7.0,
)

PROFILES = {p.name: p for p in (DEV, TEST, PORTFOLIO, ENTERPRISE)}


# Secondary fact tables: base rows at `portfolio` scale, multiplied by
# ScaleProfile.secondary_scale. Together with ScaleProfile.facts these complete
# the 85-fact enterprise model.
SECONDARY_FACTS: dict[str, int] = {
    # retail / forecourt
    "fact_retail_fuel_payments": 900_000,
    "fact_shop_returns": 60_000,
    "fact_forecourt_shift": 420_000,
    "fact_pump_meter_readings": 800_000,
    "fact_tank_dips": 700_000,
    "fact_price_changes": 260_000,
    "fact_promotions": 40_000,
    "fact_site_daily_operations": 500_000,
    # commercial / B2B
    "fact_commercial_order_lines": 900_000,
    "fact_commercial_deliveries": 380_000,
    "fact_contract_volume_commitments": 90_000,
    "fact_contract_pricing": 120_000,
    "fact_customer_invoices": 620_000,
    "fact_customer_receipts": 560_000,
    "fact_customer_credit_exposure": 300_000,
    "fact_customer_service_cases": 70_000,
    # supply, storage and logistics
    "fact_procurement_orders": 190_000,
    "fact_import_cargoes": 9_000,
    "fact_terminal_receipts": 140_000,
    "fact_terminal_issues": 210_000,
    "fact_terminal_throughput": 180_000,
    "fact_inventory_movements": 900_000,
    "fact_inventory_adjustments": 120_000,
    "fact_stock_losses": 60_000,
    "fact_replenishment_orders": 260_000,
    "fact_delivery_events": 1_100_000,
    "fact_vehicle_trips": 340_000,
    "fact_route_performance": 150_000,
    "fact_fleet_costs": 180_000,
    # LPG
    "fact_lpg_cylinder_movements": 300_000,
    "fact_lpg_bulk_deliveries": 70_000,
    "fact_lpg_inventory_snapshot": 120_000,
    # lubricants
    "fact_lubricant_orders": 150_000,
    "fact_lubricant_inventory_snapshot": 110_000,
    # aviation and marine
    "fact_aircraft_uplifts": 130_000,
    "fact_aviation_inventory_snapshot": 40_000,
    "fact_bunker_deliveries": 60_000,
    "fact_marine_inventory_snapshot": 30_000,
    # loyalty and digital
    "fact_loyalty_points_balance": 480_000,
    "fact_mobile_payments": 520_000,
    "fact_digital_sessions": 700_000,
    "fact_campaign_responses": 260_000,
    # new energy
    "fact_ev_charger_status": 400_000,
    "fact_site_energy_consumption": 600_000,
    "fact_grid_import_export": 380_000,
    "fact_energy_costs": 160_000,
    # assets and maintenance
    "fact_asset_downtime": 120_000,
    "fact_asset_inspections": 200_000,
    "fact_asset_failures": 70_000,
    "fact_spare_parts_usage": 190_000,
    "fact_asset_meter_readings": 900_000,
    # HSSEQ
    "fact_near_misses": 46_000,
    "fact_environmental_events": 22_000,
    "fact_safety_observations": 180_000,
    "fact_training_compliance": 260_000,
    "fact_permit_to_work": 150_000,
    "fact_vehicle_safety_events": 90_000,
    # finance and planning
    "fact_finance_revenue_cost": 420_000,
    "fact_general_ledger": 1_400_000,
    "fact_accounts_receivable": 380_000,
    "fact_accounts_payable": 300_000,
    "fact_capex": 40_000,
    "fact_opex": 320_000,
    "fact_budget": 260_000,
    "fact_forecast": 300_000,
    "fact_budget_vs_actual": 240_000,
    "fact_cashflow": 120_000,
    "fact_working_capital": 90_000,
    "fact_daily_executive_kpi": 380_000,
}

# Rows held in memory at once when materialising a fact table.
CHUNK_ROWS = 500_000

MIN_PORTFOLIO_FACT_ROWS = 15_000_000


def resolve(profile_name: str) -> ScaleProfile:
    if profile_name not in PROFILES:
        raise KeyError(
            f"unknown profile {profile_name!r}; choose from {sorted(PROFILES)}"
        )
    return PROFILES[profile_name]


def planned_fact_rows(profile: ScaleProfile) -> dict[str, int]:
    """Full planned row count for every fact table in the model."""
    plan = dict(profile.facts)
    for name, base in SECONDARY_FACTS.items():
        plan[name] = max(1, int(round(base * profile.secondary_scale)))
    return plan
