"""Builds the 70 conformed dimensions of the Drakens Energy 360 model.

Every name, identifier and coordinate produced here is synthetic. Site
coordinates are city centroids plus random jitter and must not be read as any
company's real network.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from . import config, names
from . import geography as geo
from . import reference as ref
from .writer import LakeWriter, logical_types


@dataclass
class DimContext:
    """Key arrays carried forward into fact generation."""

    site: pd.DataFrame
    product: pd.DataFrame
    customer: pd.DataFrame
    supplier: pd.DataFrame
    terminal: pd.DataFrame
    depot: pd.DataFrame
    vehicle: pd.DataFrame
    driver: pd.DataFrame
    employee: pd.DataFrame
    asset: pd.DataFrame
    tank: pd.DataFrame
    pump: pd.DataFrame
    loyalty: pd.DataFrame
    digital_user: pd.DataFrame
    ev_charger: pd.DataFrame
    solar_asset: pd.DataFrame
    contract: pd.DataFrame
    route: pd.DataFrame
    airport: pd.DataFrame
    port: pd.DataFrame
    date_dim: pd.DataFrame
    gl_account: pd.DataFrame
    cost_centre: pd.DataFrame
    campaign: pd.DataFrame

    # convenience arrays (populated in __post_init__)
    site_ids: np.ndarray = None
    za_site_ids: np.ndarray = None
    site_demand: np.ndarray = None
    customer_ids: np.ndarray = None
    supplier_ids: np.ndarray = None
    terminal_ids: np.ndarray = None
    vehicle_ids: np.ndarray = None
    asset_ids: np.ndarray = None

    def __post_init__(self):
        self.site_ids = self.site["site_id"].to_numpy()
        self.za_site_ids = self.site.loc[
            self.site["country_code"] == "ZA", "site_id"
        ].to_numpy()
        # Probability weights so busy sites genuinely sell more.
        d = self.site["demand_index"].to_numpy(dtype=float)
        self.site_demand = d / d.sum()
        self.customer_ids = self.customer["customer_id"].to_numpy()
        self.supplier_ids = self.supplier["supplier_id"].to_numpy()
        self.terminal_ids = self.terminal["terminal_id"].to_numpy()
        self.vehicle_ids = self.vehicle["vehicle_id"].to_numpy()
        self.asset_ids = self.asset["asset_id"].to_numpy()


def _ids(prefix: str, n: int, width: int = 7) -> np.ndarray:
    return np.array([f"{prefix}{i:0{width}d}" for i in range(1, n + 1)])


def _scd2_columns(df: pd.DataFrame, rng, effective_from: date) -> pd.DataFrame:
    """Attach Type-2 slowly changing dimension control columns."""
    df = df.copy()
    df["effective_from_date"] = pd.Timestamp(effective_from)
    df["effective_to_date"] = pd.Timestamp("9999-12-31")
    df["is_current"] = True
    df["scd_version"] = 1
    df["record_source"] = "synthetic_generator"
    df["dw_load_ts"] = pd.Timestamp(config.DATE_END) + pd.Timedelta(hours=2)
    df["dw_hash_diff"] = [
        f"{abs(hash(t)) % (16**16):016x}" for t in map(tuple, df.astype(str).values)
    ]
    return df


# ==========================================================================
# Date and time
# ==========================================================================
def build_dim_date() -> pd.DataFrame:
    days = pd.date_range(config.DATE_START, config.DATE_END, freq="D")
    df = pd.DataFrame({"full_date": days})
    df["date_key"] = df["full_date"].dt.strftime("%Y%m%d").astype(int)
    df["day_of_month"] = df["full_date"].dt.day
    df["day_of_week"] = df["full_date"].dt.dayofweek + 1
    df["day_name"] = df["full_date"].dt.day_name()
    df["day_of_year"] = df["full_date"].dt.dayofyear
    df["week_of_year"] = df["full_date"].dt.isocalendar().week.astype(int)
    df["month_number"] = df["full_date"].dt.month
    df["month_name"] = df["full_date"].dt.month_name()
    df["quarter_number"] = df["full_date"].dt.quarter
    df["quarter_name"] = "Q" + df["quarter_number"].astype(str)
    df["calendar_year"] = df["full_date"].dt.year
    # South African fiscal year runs April to March.
    df["fiscal_year"] = np.where(
        df["month_number"] >= 4, df["calendar_year"] + 1, df["calendar_year"]
    )
    df["fiscal_quarter"] = ((df["month_number"] - 4) % 12) // 3 + 1
    df["fiscal_period"] = ((df["month_number"] - 4) % 12) + 1
    df["is_weekend"] = df["day_of_week"] >= 6
    hol = set(pd.to_datetime(sorted(ref.SA_PUBLIC_HOLIDAYS)))
    df["is_public_holiday_za"] = df["full_date"].isin(hol)
    df["is_trading_day"] = True
    df["season_southern"] = df["month_number"].map(
        {12: "Summer", 1: "Summer", 2: "Summer", 3: "Autumn", 4: "Autumn",
         5: "Autumn", 6: "Winter", 7: "Winter", 8: "Winter", 9: "Spring",
         10: "Spring", 11: "Spring"}
    )
    df["school_holiday_za"] = df["month_number"].isin([1, 4, 7, 12]) & (
        df["day_of_month"] <= 15
    )
    return df[[
        "date_key", "full_date", "day_of_month", "day_of_week", "day_name",
        "day_of_year", "week_of_year", "month_number", "month_name",
        "quarter_number", "quarter_name", "calendar_year", "fiscal_year",
        "fiscal_quarter", "fiscal_period", "is_weekend", "is_public_holiday_za",
        "is_trading_day", "season_southern", "school_holiday_za",
    ]]


def build_dim_time() -> pd.DataFrame:
    mins = pd.DataFrame({"minute_of_day": range(1440)})
    mins["time_key"] = mins["minute_of_day"]
    mins["hour_24"] = mins["minute_of_day"] // 60
    mins["minute_of_hour"] = mins["minute_of_day"] % 60
    mins["time_of_day"] = mins.apply(
        lambda r: f"{r['hour_24']:02d}:{r['minute_of_hour']:02d}", axis=1
    )
    mins["day_part"] = pd.cut(
        mins["hour_24"],
        bins=[-1, 5, 9, 11, 14, 17, 20, 23],
        labels=["Overnight", "Morning Peak", "Late Morning", "Midday",
                "Afternoon", "Evening Peak", "Night"],
    ).astype(str)
    mins["is_peak_hour"] = mins["hour_24"].isin([6, 7, 8, 16, 17, 18])
    return mins[[
        "time_key", "time_of_day", "hour_24", "minute_of_hour",
        "minute_of_day", "day_part", "is_peak_hour",
    ]]


# ==========================================================================
# Geography dimensions
# ==========================================================================
def build_geography_dims(rng) -> dict[str, pd.DataFrame]:
    country = pd.DataFrame(
        geo.MARKETS, columns=["country_code", "country_name", "market_group",
                              "capital_latitude", "capital_longitude"]
    )
    country["country_key"] = np.arange(1, len(country) + 1)
    country["currency_code"] = country["country_code"].map(geo.CURRENCY_BY_COUNTRY)
    country["is_home_market"] = country["country_code"] == "ZA"

    region = pd.DataFrame(
        {"region_name": sorted({m[2] for m in geo.MARKETS})}
    )
    region["region_key"] = np.arange(1, len(region) + 1)
    region["continent"] = np.where(
        region["region_name"] == "Middle East", "Asia", "Africa"
    )

    province = pd.DataFrame({"province_name": geo.SA_PROVINCES})
    province["province_key"] = np.arange(1, len(province) + 1)
    province["country_code"] = "ZA"
    pw = geo.province_weights()
    province["network_weight"] = province["province_name"].map(pw)
    province["province_code"] = province["province_name"].map({
        "Eastern Cape": "EC", "Free State": "FS", "Gauteng": "GP",
        "KwaZulu-Natal": "KZN", "Limpopo": "LP", "Mpumalanga": "MP",
        "North West": "NW", "Northern Cape": "NC", "Western Cape": "WC",
    })

    city = pd.DataFrame([
        (a.city, a.province, "ZA", a.latitude, a.longitude, a.urban_class,
         a.n1_corridor, a.weight)
        for a in geo.SA_ANCHORS
    ], columns=["city_name", "province_name", "country_code", "latitude",
                "longitude", "urban_class", "on_national_route", "anchor_weight"])
    city["city_key"] = np.arange(1, len(city) + 1)

    currency = pd.DataFrame({
        "currency_code": sorted(set(geo.CURRENCY_BY_COUNTRY.values()))
    })
    currency["currency_key"] = np.arange(1, len(currency) + 1)
    currency["units_per_zar"] = currency["currency_code"].map(geo.FX_TO_ZAR)
    currency["is_reporting_currency"] = currency["currency_code"] == "ZAR"

    return {
        "dim_country": country, "dim_region": region, "dim_province": province,
        "dim_city": city, "dim_currency": currency,
    }


# ==========================================================================
# Network: sites, terminals, depots, warehouses
# ==========================================================================
def _site_name(rng, city: str, counts: dict[str, int]) -> str:
    """Banner plus town, numbered only when the town has more than one site."""
    counts[city] = counts.get(city, 0) + 1
    banner = rng.choice(names.SITE_BANNERS)
    n = counts[city]
    return f"{banner} {city}" if n == 1 else f"{banner} {city} {n}"


def build_dim_site(rng, profile: config.ScaleProfile) -> pd.DataFrame:
    n_za = profile.sites_za
    n_other = profile.sites_total - n_za

    weights = np.array([a.weight for a in geo.SA_ANCHORS], dtype=float)
    weights /= weights.sum()
    picks = rng.choice(len(geo.SA_ANCHORS), n_za, p=weights)

    rows = []
    # Sites are numbered within their own town, the way a real
    # network is: "Kalahari Fuels Alberton 3", not a global counter.
    city_counts: dict[str, int] = {}
    for i, idx in enumerate(picks, start=1):
        a = geo.SA_ANCHORS[idx]
        # Jitter is deliberate: roughly a 2-4 km scatter around the town
        # centroid, so no point coincides with a real station.
        jitter = 0.030 if a.urban_class == "Metro" else 0.075
        site_type = (
            "Highway Service Station" if a.n1_corridor and rng.random() < 0.35
            else {"Metro": "Urban Service Station",
                  "Urban": "Urban Service Station",
                  "Town": "Rural Service Station",
                  "Rural": "Rural Service Station"}[a.urban_class]
        )
        if rng.random() < 0.05:
            site_type = "Truck Stop"
        rows.append((
            f"S{i:06d}",
            _site_name(rng, a.city, city_counts),
            "ZA", a.province, a.city, a.urban_class,
            float(a.latitude + rng.normal(0, jitter)),
            float(a.longitude + rng.normal(0, jitter)),
            site_type,
            str(rng.choice(ref.OWNERSHIP_MODELS, p=[0.12, 0.58, 0.30])),
            bool(a.n1_corridor and rng.random() < 0.55),
        ))

    other_codes = [m[0] for m in geo.MARKETS if m[0] != "ZA"]
    centroid = {m[0]: (m[3], m[4]) for m in geo.MARKETS}
    share = rng.dirichlet(np.ones(len(other_codes)) * 2.0)
    assigned = rng.choice(other_codes, n_other, p=share)
    for j, cc in enumerate(assigned, start=n_za + 1):
        lat, lon = centroid[cc]
        rows.append((
            f"S{j:06d}",
            f"{rng.choice(names.SITE_BANNERS)} {cc} {j:05d}",
            cc, None, None, "Urban",
            float(lat + rng.normal(0, 0.45)),
            float(lon + rng.normal(0, 0.45)),
            str(rng.choice(ref.SITE_TYPES[:5])),
            str(rng.choice(ref.OWNERSHIP_MODELS, p=[0.12, 0.58, 0.30])),
            bool(rng.random() < 0.25),
        ))

    site = pd.DataFrame(rows, columns=[
        "site_id", "site_name", "country_code", "province", "city",
        "urban_class", "latitude", "longitude", "site_type",
        "ownership_model", "on_national_route",
    ])
    n = len(site)
    site["site_key"] = np.arange(1, n + 1)
    site["forecourt_lanes"] = rng.integers(2, 13, n)
    site["has_convenience"] = rng.random(n) < 0.68
    site["has_qsr"] = rng.random(n) < 0.31
    site["has_car_wash"] = rng.random(n) < 0.27
    site["has_ev_charging"] = rng.random(n) < 0.15
    site["has_solar"] = rng.random(n) < 0.12
    site["has_lpg"] = rng.random(n) < 0.44
    site["is_24_hour"] = rng.random(n) < 0.52
    site["opened_date"] = pd.to_datetime(
        rng.choice(pd.date_range("1998-01-01", "2026-01-01"), n)
    )
    site["site_status"] = np.where(rng.random(n) < 0.972, "Operating", "Temporarily Closed")

    # A single multiplier driving how busy each site is. Metro highway sites
    # with a shop trade far harder than a rural single-product site, and this
    # is what makes the fact data non-uniform.
    base = np.where(site["urban_class"] == "Metro", 1.45,
           np.where(site["urban_class"] == "Urban", 1.10,
           np.where(site["urban_class"] == "Town", 0.80, 0.55)))
    base = base * np.where(site["on_national_route"], 1.30, 1.0)
    base = base * np.where(site["site_type"] == "Truck Stop", 1.55, 1.0)
    base = base * np.where(site["has_convenience"], 1.12, 1.0)
    base = base * np.where(site["country_code"] == "ZA", 1.0, 0.85)
    base = base * rng.lognormal(0.0, 0.34, n)          # site-level idiosyncrasy
    base = base * np.where(site["site_status"] == "Operating", 1.0, 0.05)
    site["demand_index"] = np.round(base, 4)
    return site


def build_dim_terminal(rng, profile) -> pd.DataFrame:
    n = profile.terminals
    towns = geo.SA_TERMINAL_TOWNS
    rows = []
    for i in range(1, n + 1):
        if i <= len(towns):
            prov, city, seed_name = towns[i - 1]
            cc = "ZA"
            name = f"{seed_name} Fuel Terminal"
        else:
            cc = str(rng.choice([m[0] for m in geo.MARKETS]))
            prov = city = None
            name = f"{rng.choice(names.STEM_A)} Fuel Terminal"
        rows.append((f"T{i:04d}", name, cc, prov, city))
    t = pd.DataFrame(rows, columns=[
        "terminal_id", "terminal_name", "country_code", "province", "city"
    ])
    t["terminal_key"] = np.arange(1, n + 1)
    t["capacity_litres"] = rng.integers(3_000_000, 130_000_000, n)
    t["tank_count"] = rng.integers(4, 40, n)
    t["pipeline_connected"] = rng.random(n) < 0.30
    t["rail_connected"] = rng.random(n) < 0.35
    t["port_connected"] = rng.random(n) < 0.40
    t["road_gantry_bays"] = rng.integers(2, 16, n)
    t["commissioned_year"] = rng.integers(1965, 2024, n)
    return t


def build_dim_depot(rng, profile, terminal) -> pd.DataFrame:
    n = profile.depots
    d = pd.DataFrame({
        "depot_id": _ids("DEP", n, 4),
        "depot_key": np.arange(1, n + 1),
        "depot_name": [f"{x} Depot" for x in rng.choice(names.STEM_A, n)],
        "parent_terminal_id": rng.choice(terminal["terminal_id"], n),
        "country_code": rng.choice(terminal["country_code"], n),
        "storage_capacity_litres": rng.integers(200_000, 9_000_000, n),
        "serves_lpg": rng.random(n) < 0.4,
        "serves_lubricants": rng.random(n) < 0.55,
    })
    return d


def build_dim_warehouse(rng, profile, depot) -> pd.DataFrame:
    n = max(8, profile.depots // 2)
    return pd.DataFrame({
        "warehouse_id": _ids("WH", n, 4),
        "warehouse_key": np.arange(1, n + 1),
        "warehouse_name": [f"{x} Distribution Centre"
                           for x in rng.choice(names.STEM_A, n)],
        "linked_depot_id": rng.choice(depot["depot_id"], n),
        "pallet_positions": rng.integers(400, 9_000, n),
        "temperature_controlled": rng.random(n) < 0.2,
    })


# ==========================================================================
# Product dimensions
# ==========================================================================
def build_product_dims(rng) -> dict[str, pd.DataFrame]:
    p = pd.DataFrame(ref.PRODUCTS)
    p["product_key"] = np.arange(1, len(p) + 1)
    p["brand"] = rng.choice(ref.PRODUCT_BRANDS, len(p))
    p["hazard_class"] = np.where(
        p["category"].isin(["Fuel", "LPG"]), "Flammable", "Non-Hazardous"
    )
    p["shelf_life_days"] = np.where(p["category"] == "Convenience",
                                    rng.integers(3, 400, len(p)), 0)

    cat = pd.DataFrame({"category_name": sorted(p["category"].unique())})
    cat["category_key"] = np.arange(1, len(cat) + 1)
    cat["is_regulated_price"] = cat["category_name"].isin(["Fuel", "LPG"])
    cat["margin_profile"] = cat["category_name"].map({
        "Fuel": "Low", "LPG": "Low", "Lubricant": "High",
        "Convenience": "High", "Energy": "Medium",
    })

    brand = pd.DataFrame({"brand_name": ref.PRODUCT_BRANDS})
    brand["brand_key"] = np.arange(1, len(brand) + 1)
    brand["is_own_label"] = brand["brand_name"] != "Unbranded"

    uom = pd.DataFrame({
        "uom_code": ["L", "KG", "EA", "KWH", "M3", "T"],
        "uom_name": ["Litre", "Kilogram", "Each", "Kilowatt Hour",
                     "Cubic Metre", "Tonne"],
        "uom_type": ["Volume", "Mass", "Count", "Energy", "Volume", "Mass"],
        "base_conversion": [1.0, 1.0, 1.0, 1.0, 1000.0, 1000.0],
    })
    uom["uom_key"] = np.arange(1, len(uom) + 1)
    return {
        "dim_product": p, "dim_product_category": cat,
        "dim_product_brand": brand, "dim_unit_of_measure": uom,
    }


# ==========================================================================
# Party dimensions: customer, supplier, employee
# ==========================================================================
def build_dim_customer(rng, profile) -> pd.DataFrame:
    n = profile.customers
    sector = rng.choice(ref.CUSTOMER_SECTORS, n, p=_sector_probs())
    segment = rng.choice(ref.CUSTOMER_SEGMENTS, n, p=[0.02, 0.08, 0.20, 0.45, 0.25])
    df = pd.DataFrame({
        "customer_id": _ids("C", n),
        "customer_key": np.arange(1, n + 1),
        "customer_name": names.company_names(rng, sector, n),
        "sector": sector,
        "segment": segment,
        "country_code": rng.choice([m[0] for m in geo.MARKETS], n,
                                   p=_country_probs()),
        "credit_band": rng.choice(list("ABCD"), n, p=[0.28, 0.42, 0.23, 0.07]),
        "credit_limit_zar": np.round(rng.lognormal(12.4, 1.35, n), -2),
        "payment_terms_days": rng.choice([0, 7, 14, 30, 45, 60], n,
                                         p=[0.16, 0.10, 0.14, 0.40, 0.12, 0.08]),
        "onboarded_date": pd.to_datetime(
            rng.choice(pd.date_range("2010-01-01", "2026-06-30"), n)
        ),
        "is_active": rng.random(n) < 0.93,
    })
    # Segment drives order size later on.
    df["revenue_index"] = df["segment"].map({
        "Strategic": 22.0, "Key Account": 8.5, "Mid Market": 3.0,
        "Small Business": 1.0, "Spot": 0.6,
    }) * rng.lognormal(0, 0.5, n)
    return df


def _sector_probs():
    p = np.array([0.20, 0.14, 0.11, 0.05, 0.04, 0.03, 0.09, 0.10,
                  0.05, 0.08, 0.09, 0.02])
    return p / p.sum()


def _country_probs():
    # South Africa dominates; the rest of the footprint tapers off.
    n = len(geo.MARKETS)
    p = np.full(n, 0.6 / (n - 1))
    p[0] = 0.40
    return p / p.sum()


def build_dim_supplier(rng, profile) -> pd.DataFrame:
    n = profile.suppliers
    supplier_type = rng.choice(ref.SUPPLIER_TYPES, n)
    return pd.DataFrame({
        "supplier_id": _ids("SUP", n, 5),
        "supplier_key": np.arange(1, n + 1),
        "supplier_name": names.supplier_names(rng, supplier_type, n),
        "supplier_type": supplier_type,
        "country_code": rng.choice([m[0] for m in geo.MARKETS], n),
        "risk_rating": rng.choice(["Low", "Medium", "High"], n, p=[0.65, 0.28, 0.07]),
        "esg_score": np.round(rng.beta(6, 3, n) * 100, 1),
        "preferred_supplier": rng.random(n) < 0.32,
        "contract_start_date": pd.to_datetime(
            rng.choice(pd.date_range("2015-01-01", "2026-01-01"), n)
        ),
    })


def build_dim_employee(rng, profile, site) -> pd.DataFrame:
    n = profile.employees
    return pd.DataFrame({
        "employee_id": _ids("E", n, 7),
        "employee_key": np.arange(1, n + 1),
        "employee_name": names.person_names(rng, n),
        "role": rng.choice(ref.ROLES, n),
        "home_site_id": rng.choice(site["site_id"], n),
        "business_unit_code": rng.choice([b[0] for b in ref.BUSINESS_UNITS], n),
        "employment_type": rng.choice(["Permanent", "Fixed Term", "Contractor"],
                                      n, p=[0.72, 0.18, 0.10]),
        "hire_date": pd.to_datetime(
            rng.choice(pd.date_range("2008-01-01", "2026-06-30"), n)
        ),
        "is_active": rng.random(n) < 0.91,
    })


# ==========================================================================
# Asset dimensions
# ==========================================================================
def build_asset_dims(rng, profile, site) -> dict[str, pd.DataFrame]:
    n = profile.assets
    site_ids = site["site_id"].to_numpy()
    asset = pd.DataFrame({
        "asset_id": _ids("A", n, 7),
        "asset_key": np.arange(1, n + 1),
        "site_id": rng.choice(site_ids, n),
        "asset_type": rng.choice(ref.ASSET_TYPES, n),
        "manufacturer": rng.choice(
            ["Aurex Dispensing", "Meridian Fuel Systems",
             "Corvus Industrial", "Talon Forecourt Systems"], n
        ),
        "model_code": [f"MDL-{x:04d}" for x in rng.integers(1000, 9999, n)],
        "install_date": pd.to_datetime(
            rng.choice(pd.date_range("2005-01-01", "2026-06-30"), n)
        ),
        "replacement_value_zar": np.round(rng.lognormal(11.6, 0.9, n), -2),
        "criticality": rng.choice(["Low", "Medium", "High", "Critical"], n,
                                  p=[0.30, 0.40, 0.23, 0.07]),
    })
    age_years = (
        pd.Timestamp(config.DATE_END) - asset["install_date"]
    ).dt.days / 365.25
    asset["age_years"] = np.round(age_years, 2)
    # Older, more critical assets fail more often. Used by the predictive
    # maintenance fact and the ML feature set.
    asset["failure_propensity"] = np.round(
        (0.02 + 0.011 * age_years)
        * asset["criticality"].map(
            {"Low": 0.7, "Medium": 1.0, "High": 1.35, "Critical": 1.8}
        )
        * rng.lognormal(0, 0.3, n),
        5,
    )

    asset_type = pd.DataFrame({"asset_type_name": ref.ASSET_TYPES})
    asset_type["asset_type_key"] = np.arange(1, len(asset_type) + 1)
    asset_type["maintenance_interval_days"] = rng.choice(
        [30, 60, 90, 180, 365], len(asset_type)
    )
    asset_type["requires_statutory_inspection"] = asset_type[
        "asset_type_name"
    ].isin(["Underground Tank", "Aboveground Tank", "Fire Suppression System"])

    n_eq = max(20, profile.assets // 4)
    equipment = pd.DataFrame({
        "equipment_id": _ids("EQ", n_eq, 6),
        "equipment_key": np.arange(1, n_eq + 1),
        "parent_asset_id": rng.choice(asset["asset_id"], n_eq),
        "equipment_name": rng.choice(
            ["Motor", "Meter", "Nozzle", "Valve", "Controller", "Sensor"], n_eq
        ),
        "serial_number": [f"SN{x:09d}" for x in rng.integers(1, 10**9, n_eq)],
    })

    n_t = profile.tanks
    tank = pd.DataFrame({
        "tank_id": _ids("TK", n_t, 6),
        "tank_key": np.arange(1, n_t + 1),
        "site_id": rng.choice(site_ids, n_t),
        "product_id": rng.choice(ref.ROAD_FUEL_IDS, n_t),
        "capacity_litres": rng.choice([9000, 12000, 23000, 30000, 46000], n_t),
        "tank_material": rng.choice(["Steel", "GRP", "Double Skin Steel"], n_t),
        "install_year": rng.integers(1990, 2026, n_t),
        "has_leak_detection": rng.random(n_t) < 0.78,
        "telemetry_enabled": rng.random(n_t) < 0.83,
    })

    n_p = profile.pumps
    pump = pd.DataFrame({
        "pump_id": _ids("PM", n_p, 6),
        "pump_key": np.arange(1, n_p + 1),
        "site_id": rng.choice(site_ids, n_p),
        "pump_number": rng.integers(1, 13, n_p),
        "nozzle_count": rng.choice([2, 3, 4, 6], n_p),
        "flow_rate_lpm": np.round(rng.normal(40, 8, n_p).clip(18, 130), 1),
        "supports_high_flow_diesel": rng.random(n_p) < 0.22,
    })

    n_ev = profile.ev_chargers
    ev = pd.DataFrame({
        "ev_charger_id": _ids("EVC", n_ev, 5),
        "ev_charger_key": np.arange(1, n_ev + 1),
        "site_id": rng.choice(
            site.loc[site["has_ev_charging"], "site_id"].to_numpy()
            if site["has_ev_charging"].any() else site_ids, n_ev
        ),
        "connector_type": rng.choice(["CCS2", "CHAdeMO", "Type 2 AC"], n_ev,
                                     p=[0.62, 0.10, 0.28]),
        "rated_power_kw": rng.choice([22, 60, 80, 120, 150, 180], n_ev),
        "commissioned_date": pd.to_datetime(
            rng.choice(pd.date_range("2021-01-01", "2026-06-30"), n_ev)
        ),
        "network_operator": rng.choice(
            ["Voltway Charging", "Amperion E-Mobility",
             "Zenith Charge Network"], n_ev
        ),
    })

    n_sol = profile.solar_assets
    solar = pd.DataFrame({
        "solar_asset_id": _ids("SOL", n_sol, 5),
        "solar_asset_key": np.arange(1, n_sol + 1),
        "site_id": rng.choice(
            site.loc[site["has_solar"], "site_id"].to_numpy()
            if site["has_solar"].any() else site_ids, n_sol
        ),
        "installed_kwp": np.round(rng.uniform(15, 320, n_sol), 1),
        "panel_count": rng.integers(30, 700, n_sol),
        "inverter_model": rng.choice(["SYN-INV-5K", "SYN-INV-12K", "SYN-INV-30K"], n_sol),
        "commissioned_date": pd.to_datetime(
            rng.choice(pd.date_range("2020-01-01", "2026-06-30"), n_sol)
        ),
        "has_battery_storage": rng.random(n_sol) < 0.34,
    })
    return {
        "dim_asset": asset, "dim_asset_type": asset_type,
        "dim_equipment": equipment, "dim_tank": tank, "dim_pump": pump,
        "dim_ev_charger": ev, "dim_solar_asset": solar,
    }


# ==========================================================================
# Logistics dimensions
# ==========================================================================
def build_logistics_dims(rng, profile, site, terminal) -> dict[str, pd.DataFrame]:
    n_c = max(20, profile.vehicles // 40)
    carrier = pd.DataFrame({
        "carrier_id": _ids("CAR", n_c, 4),
        "carrier_key": np.arange(1, n_c + 1),
        "carrier_name": names.carrier_names(rng, n_c),
        "is_own_fleet": rng.random(n_c) < 0.35,
        "fleet_size": rng.integers(3, 260, n_c),
        "safety_rating": rng.choice(["A", "B", "C"], n_c, p=[0.5, 0.38, 0.12]),
    })

    n_v = profile.vehicles
    vehicle = pd.DataFrame({
        "vehicle_id": _ids("V", n_v, 6),
        "vehicle_key": np.arange(1, n_v + 1),
        "carrier_id": rng.choice(carrier["carrier_id"], n_v),
        "vehicle_type": rng.choice(
            ["Rigid Fuel Tanker", "Articulated Fuel Tanker", "LPG Tanker",
             "Lubricant Truck", "Light Delivery Vehicle"],
            n_v, p=[0.28, 0.44, 0.12, 0.10, 0.06]),
        "capacity_litres": rng.choice([8000, 18000, 24000, 32000, 36000, 44000], n_v),
        "compartments": rng.choice([1, 3, 4, 5, 6], n_v),
        "model_year": rng.integers(2008, 2027, n_v),
        "telematics_enabled": rng.random(n_v) < 0.86,
        "is_active": rng.random(n_v) < 0.94,
    })

    n_d = profile.drivers
    driver = pd.DataFrame({
        "driver_id": _ids("DRV", n_d, 6),
        "driver_key": np.arange(1, n_d + 1),
        "driver_name": names.person_names(rng, n_d),
        "carrier_id": rng.choice(carrier["carrier_id"], n_d),
        "licence_class": rng.choice(["EC", "EB", "C1"], n_d, p=[0.72, 0.18, 0.10]),
        "hazmat_certified": rng.random(n_d) < 0.81,
        "years_experience": rng.integers(0, 35, n_d),
        "safety_score": np.round(rng.beta(7, 2, n_d) * 100, 1),
    })

    n_r = profile.routes
    origin = rng.choice(terminal["terminal_id"], n_r)
    route = pd.DataFrame({
        "route_id": _ids("RT", n_r, 6),
        "route_key": np.arange(1, n_r + 1),
        "origin_terminal_id": origin,
        "route_name": [f"{a} - {b}" for a, b in
                       zip(rng.choice(names.STEM_A, n_r),
                           rng.choice(names.STEM_A, n_r), strict=False)],
        "planned_distance_km": np.round(
            rng.gamma(2.3, 105, n_r).clip(4, 1500), 1),
        "route_class": rng.choice(["Urban", "Regional", "Long Haul"], n_r,
                                  p=[0.42, 0.38, 0.20]),
        "drop_count": rng.integers(1, 9, n_r),
    })
    route["planned_duration_hours"] = np.round(
        route["planned_distance_km"] / rng.uniform(42, 68, n_r)
        + route["drop_count"] * 0.55, 2
    )
    return {
        "dim_carrier": carrier, "dim_vehicle": vehicle,
        "dim_driver": driver, "dim_route": route,
    }


# ==========================================================================
# Commercial, digital and finance dimensions
# ==========================================================================
def build_commercial_dims(rng, profile, customer) -> dict[str, pd.DataFrame]:
    n_k = profile.contracts
    start = pd.to_datetime(rng.choice(pd.date_range("2021-01-01", "2026-03-01"), n_k))
    contract = pd.DataFrame({
        "contract_id": _ids("CT", n_k, 6),
        "contract_key": np.arange(1, n_k + 1),
        "customer_id": rng.choice(customer["customer_id"], n_k),
        "contract_type": rng.choice(ref.CONTRACT_TYPES, n_k,
                                    p=[0.34, 0.22, 0.24, 0.08, 0.12]),
        "start_date": start,
        "end_date": start + pd.to_timedelta(rng.integers(180, 1460, n_k), unit="D"),
        "committed_volume_litres": np.round(rng.lognormal(12.2, 1.5, n_k), -2),
        "price_mechanism": rng.choice(
            ["Basic Fuel Price Linked", "Fixed", "Index Linked", "Cost Plus"],
            n_k, p=[0.46, 0.16, 0.24, 0.14]),
        "discount_cents_per_litre": np.round(rng.gamma(2.0, 18.0, n_k).clip(0, 190), 1),
    })

    ctype = pd.DataFrame({"contract_type_name": ref.CONTRACT_TYPES})
    ctype["contract_type_key"] = np.arange(1, len(ctype) + 1)
    ctype["requires_volume_commitment"] = ctype["contract_type_name"].isin(
        ["Long-term Supply", "Annual Tender", "Framework"])

    seg = pd.DataFrame({"segment_name": ref.CUSTOMER_SEGMENTS})
    seg["segment_key"] = np.arange(1, len(seg) + 1)
    seg["service_tier"] = ["Platinum", "Gold", "Silver", "Bronze", "Transactional"]

    sec = pd.DataFrame({"sector_name": ref.CUSTOMER_SECTORS})
    sec["sector_key"] = np.arange(1, len(sec) + 1)
    sec["is_industrial"] = sec["sector_name"].isin(
        ["Mining", "Construction", "Power Generation", "Manufacturing"])

    channel = pd.DataFrame({"channel_name": ref.CHANNELS})
    channel["channel_key"] = np.arange(1, len(channel) + 1)
    channel["is_digital"] = channel["channel_name"] == "Digital App"

    pay = pd.DataFrame({"payment_method_name": ref.PAYMENT_METHODS})
    pay["payment_method_key"] = np.arange(1, len(pay) + 1)
    pay["is_cashless"] = pay["payment_method_name"] != "Cash"
    pay["settlement_days"] = [1, 0, 2, 1, 30, 7]

    n_promo = max(20, int(400 * profile.secondary_scale) + 20)
    pstart = pd.to_datetime(rng.choice(
        pd.date_range(config.DATE_START, config.DATE_END), n_promo))
    promo = pd.DataFrame({
        "promotion_id": _ids("PRM", n_promo, 5),
        "promotion_key": np.arange(1, n_promo + 1),
        "promotion_name": [f"{a} {b}" for a, b in zip(
            rng.choice(["Summer", "Winter", "Payday", "Road Trip",
                        "Weekend", "Fuel Up", "Commuter", "Holiday"], n_promo),
            rng.choice(["Rewards", "Saver", "Bonus Points", "Cashback",
                        "Double Points", "Value Deal"], n_promo), strict=False)],
        "mechanic": rng.choice(
            ["Price Off", "Bundle", "Points Multiplier", "Free Item", "Fuel Voucher"],
            n_promo),
        "start_date": pstart,
        "end_date": pstart + pd.to_timedelta(rng.integers(7, 90, n_promo), unit="D"),
        "discount_pct": np.round(rng.uniform(0.02, 0.35, n_promo), 3),
    })

    n_zone = 30
    zone = pd.DataFrame({
        "price_zone_id": _ids("PZ", n_zone, 3),
        "price_zone_key": np.arange(1, n_zone + 1),
        "zone_name": [f"Pricing Zone {i:02d}" for i in range(1, n_zone + 1)],
        "inland_or_coastal": rng.choice(["Inland", "Coastal"], n_zone, p=[0.62, 0.38]),
        "zone_differential_cents": np.round(rng.normal(0, 28, n_zone), 1),
    })

    tax = pd.DataFrame({
        "tax_code": ["VAT15", "FUELLEVY", "RAF", "CARBON", "ZERO"],
        "tax_key": [1, 2, 3, 4, 5],
        "tax_name": ["Value Added Tax", "General Fuel Levy",
                     "Road Accident Fund Levy", "Carbon Fuel Levy", "Zero Rated"],
        "tax_rate": [0.15, 0.0, 0.0, 0.0, 0.0],
        "tax_cents_per_litre": [0.0, 396.0, 218.0, 11.0, 0.0],
        "tax_type": ["Ad Valorem", "Specific", "Specific", "Specific", "None"],
    })
    return {
        "dim_contract": contract, "dim_contract_type": ctype,
        "dim_customer_segment": seg, "dim_customer_sector": sec,
        "dim_channel": channel, "dim_payment_method": pay,
        "dim_promotion": promo, "dim_price_zone": zone, "dim_tax": tax,
    }


def build_digital_dims(rng, profile, site) -> dict[str, pd.DataFrame]:
    n_l = profile.loyalty_members
    joined = pd.to_datetime(rng.choice(pd.date_range("2019-01-01", "2026-08-01"), n_l))
    loyalty = pd.DataFrame({
        "loyalty_member_id": _ids("LM", n_l, 9),
        "loyalty_member_key": np.arange(1, n_l + 1),
        "tier": rng.choice(["Blue", "Silver", "Gold", "Platinum"], n_l,
                           p=[0.55, 0.28, 0.13, 0.04]),
        "joined_date": joined,
        "home_site_id": rng.choice(site["site_id"], n_l),
        "opt_in_marketing": rng.random(n_l) < 0.61,
        "is_active": rng.random(n_l) < 0.72,
    })

    n_u = profile.digital_users
    digital = pd.DataFrame({
        "digital_user_id": _ids("DU", n_u, 9),
        "digital_user_key": np.arange(1, n_u + 1),
        "registered_date": pd.to_datetime(
            rng.choice(pd.date_range("2020-01-01", "2026-08-01"), n_u)),
        "primary_device_type": rng.choice(ref.DEVICE_TYPES, n_u,
                                          p=[0.44, 0.24, 0.06, 0.10, 0.14, 0.02]),
        "app_version": rng.choice(["3.2.1", "3.3.0", "4.0.2", "4.1.0"], n_u),
        "push_enabled": rng.random(n_u) < 0.58,
        "linked_loyalty_member_id": np.where(
            rng.random(n_u) < 0.66,
            rng.choice(loyalty["loyalty_member_id"], n_u), None),
    })

    device = pd.DataFrame({"device_type_name": ref.DEVICE_TYPES})
    device["device_key"] = np.arange(1, len(device) + 1)
    device["is_mobile"] = ~device["device_type_name"].isin(["Desktop Web", "Kiosk"])

    n_camp = max(20, int(300 * profile.secondary_scale) + 20)
    cstart = pd.to_datetime(rng.choice(
        pd.date_range(config.DATE_START, config.DATE_END), n_camp))
    campaign = pd.DataFrame({
        "campaign_id": _ids("CMP", n_camp, 5),
        "campaign_key": np.arange(1, n_camp + 1),
        "campaign_name": [f"{a} {b}" for a, b in zip(
            rng.choice(["Q1", "Q2", "Q3", "Q4", "Winter", "Summer",
                        "Back to School", "Festive"], n_camp),
            rng.choice(["Loyalty Drive", "App Adoption", "Fuel Rewards",
                        "Shop Offer", "EV Launch", "Fleet Push"], n_camp), strict=False)],
        "channel": rng.choice(ref.CAMPAIGN_CHANNELS, n_camp),
        "start_date": cstart,
        "end_date": cstart + pd.to_timedelta(rng.integers(5, 60, n_camp), unit="D"),
        "budget_zar": np.round(rng.lognormal(11.0, 1.0, n_camp), -2),
        "target_segment": rng.choice(ref.CUSTOMER_SEGMENTS, n_camp),
    })
    return {
        "dim_loyalty_member": loyalty, "dim_digital_user": digital,
        "dim_device": device, "dim_campaign": campaign,
    }


def build_finance_dims(rng, profile) -> dict[str, pd.DataFrame]:
    bu = pd.DataFrame(ref.BUSINESS_UNITS,
                      columns=["business_unit_code", "business_unit_name", "segment"])
    bu["business_unit_key"] = np.arange(1, len(bu) + 1)

    entity = pd.DataFrame({
        "legal_entity_code": [f"LE{i:02d}" for i in range(1, 13)],
        "legal_entity_key": np.arange(1, 13),
        "legal_entity_name": [f"{x} Energy Holdings" for x in
                              rng.choice(names.STEM_A, 12, replace=False)],
        "country_code": rng.choice([m[0] for m in geo.MARKETS], 12),
        "functional_currency": rng.choice(["ZAR", "USD", "EUR"], 12, p=[0.6, 0.3, 0.1]),
        "consolidation_method": rng.choice(["Full", "Equity"], 12, p=[0.85, 0.15]),
    })

    cc = pd.DataFrame({"cost_centre_name": ref.COST_CENTRES})
    cc["cost_centre_key"] = np.arange(1, len(cc) + 1)
    cc["cost_centre_code"] = [f"CC{i:03d}" for i in range(1, len(cc) + 1)]
    cc["function"] = np.where(
        cc["cost_centre_name"].isin(["Finance", "IT and Digital", "Human Resources", "HSSEQ"]),
        "Support", "Operations")

    pc = pd.DataFrame({
        "profit_centre_code": [f"PC{i:03d}" for i in range(1, 21)],
        "profit_centre_key": np.arange(1, 21),
        "profit_centre_name": [f"{a} {b}" for a, b in zip(
            rng.choice(names.STEM_A, 20),
            rng.choice(["Retail", "Commercial", "Supply", "Lubricants",
                        "LPG", "New Energy"], 20), strict=False)],
        "business_unit_code": rng.choice(bu["business_unit_code"], 20),
    })

    gl = pd.DataFrame(ref.GL_ACCOUNTS,
                      columns=["gl_account_code", "gl_account_name", "account_class"])
    gl["gl_account_key"] = np.arange(1, len(gl) + 1)
    gl["normal_balance"] = np.where(
        gl["account_class"].isin(["Revenue"]), "Credit", "Debit")
    gl["is_pnl"] = gl["account_class"].isin(["Revenue", "COGS", "Opex"])

    role = pd.DataFrame({"role_name": ref.ROLES})
    role["role_key"] = np.arange(1, len(role) + 1)
    role["role_family"] = np.where(
        role["role_name"].isin(["Site Manager", "Area Manager", "Planner"]),
        "Management", "Operational")

    scenario = pd.DataFrame({"scenario_name": ref.SCENARIOS})
    scenario["scenario_key"] = np.arange(1, len(scenario) + 1)
    scenario["is_actual"] = scenario["scenario_name"] == "Actual"

    budget_v = pd.DataFrame({
        "budget_version_code": ["BUD-FY25", "BUD-FY26", "BUD-FY27", "BUD-FY26-R1"],
        "budget_version_key": [1, 2, 3, 4],
        "fiscal_year": [2025, 2026, 2027, 2026],
        "version_status": ["Locked", "Locked", "Draft", "Locked"],
    })

    forecast_v = pd.DataFrame({
        "forecast_version_code": [f"FC-{y}-{m}" for y in (2025, 2026) for m in ("Q1", "Q2", "Q3", "Q4")],
        "forecast_version_key": np.arange(1, 9),
        "forecast_type": ["Rolling"] * 8,
        "published_flag": [True] * 6 + [False] * 2,
    })
    return {
        "dim_business_unit": bu, "dim_legal_entity": entity,
        "dim_cost_centre": cc, "dim_profit_centre": pc, "dim_gl_account": gl,
        "dim_role": role, "dim_scenario": scenario,
        "dim_budget_version": budget_v, "dim_forecast_version": forecast_v,
    }


def build_operational_code_dims(rng, profile) -> dict[str, pd.DataFrame]:
    def code_dim(name_col, values, key_col, **extra):
        df = pd.DataFrame({name_col: values})
        df[key_col] = np.arange(1, len(values) + 1)
        for k, v in extra.items():
            df[k] = v
        return df

    incident_type = code_dim("incident_type_name", ref.INCIDENT_TYPES, "incident_type_key")
    incident_type["is_process_safety"] = incident_type["incident_type_name"].isin(
        ["Fire", "Fuel Spill", "Process Safety", "Chemical Exposure"])

    severity = code_dim("severity_name", ref.INCIDENT_SEVERITIES, "incident_severity_key")
    severity["severity_rank"] = [1, 2, 3, 4, 5]
    severity["is_reportable"] = severity["severity_rank"] >= 3

    maint = code_dim("maintenance_type_name", ref.MAINTENANCE_TYPES, "maintenance_type_key")
    maint["is_planned"] = maint["maintenance_type_name"].isin(
        ["Preventive", "Predictive", "Statutory Inspection"])

    fail = code_dim("failure_mode_name", ref.FAILURE_MODES, "failure_mode_key")
    fail["typical_repair_hours"] = rng.uniform(0.5, 26, len(ref.FAILURE_MODES)).round(1)

    site_type = code_dim("site_type_name", ref.SITE_TYPES, "site_type_key")
    site_type["is_retail"] = ~site_type["site_type_name"].isin(
        ["Marine Bunkering Point", "Airport Fuel Farm"])

    sup_type = code_dim("supplier_type_name", ref.SUPPLIER_TYPES, "supplier_type_key")
    sup_type["is_logistics"] = sup_type["supplier_type_name"].isin(
        ["Road Transporter", "Rail Operator", "Pipeline Operator"])

    delivery_status = code_dim("delivery_status_name", ref.DELIVERY_STATUSES, "delivery_status_key")
    delivery_status["is_terminal_state"] = delivery_status["delivery_status_name"].isin(
        ["Delivered", "Short Delivered", "Failed"])

    order_status = code_dim("order_status_name", ref.ORDER_STATUSES, "order_status_key")
    order_status["is_open"] = order_status["order_status_name"].isin(
        ["Draft", "Confirmed", "Allocated"])

    shift = code_dim("shift_name", ref.SHIFTS, "shift_key")
    shift["start_hour"] = [6, 14, 22]
    shift["end_hour"] = [14, 22, 6]

    lane = pd.DataFrame({"lane_number": np.arange(1, 13)})
    lane["forecourt_lane_key"] = lane["lane_number"]
    lane["lane_type"] = np.where(lane["lane_number"] <= 8, "Light Vehicle", "Heavy Vehicle")

    reason = code_dim("reason_code_name", ref.REASON_CODES, "reason_code_key")
    reason["reason_category"] = rng.choice(
        ["Supply", "Logistics", "Customer", "Quality", "External"], len(ref.REASON_CODES))

    energy = code_dim("energy_source_name", ref.ENERGY_SOURCES, "energy_source_key")
    energy["is_renewable"] = energy["energy_source_name"].isin(["Solar PV", "Battery Storage"])
    energy["kg_co2_per_kwh"] = [0.95, 0.0, 0.72, 0.05]

    lpg_cyl = pd.DataFrame({
        "cylinder_type_code": ["C9", "C19", "C48", "BULK"],
        "lpg_cylinder_type_key": [1, 2, 3, 4],
        "nominal_kg": [9.0, 19.0, 48.0, 0.0],
        "deposit_zar": [420.0, 780.0, 1450.0, 0.0],
        "is_returnable": [True, True, True, False],
    })

    weather = pd.DataFrame({"weather_condition": ref.WEATHER_CONDITIONS})
    weather["weather_key"] = np.arange(1, len(ref.WEATHER_CONDITIONS) + 1)
    weather["demand_impact_pct"] = [0.0, -0.01, -0.05, -0.14, -0.03, -0.09, 0.04]

    src = pd.DataFrame(ref.DATA_SOURCES,
                       columns=["data_source_code", "data_source_name",
                                "ingestion_pattern", "owning_domain"])
    src["data_source_key"] = np.arange(1, len(src) + 1)
    src["sla_minutes"] = np.where(src["ingestion_pattern"] == "Event Stream", 15,
                          np.where(src["ingestion_pattern"] == "CDC", 60, 240))
    src["is_pii_bearing"] = src["data_source_code"].isin(
        ["SRC09", "SRC10", "SRC11"])
    return {
        "dim_incident_type": incident_type, "dim_incident_severity": severity,
        "dim_maintenance_type": maint, "dim_failure_mode": fail,
        "dim_site_type": site_type, "dim_supplier_type": sup_type,
        "dim_delivery_status": delivery_status, "dim_order_status": order_status,
        "dim_shift": shift, "dim_forecourt_lane": lane,
        "dim_reason_code": reason, "dim_energy_source": energy,
        "dim_lpg_cylinder_type": lpg_cyl, "dim_weather": weather,
        "dim_data_source": src,
    }


def build_transport_node_dims(rng, profile) -> dict[str, pd.DataFrame]:
    ap = pd.DataFrame(geo.SA_AIRPORTS,
                      columns=["iata_code", "airport_name", "province", "city"])
    ap["airport_key"] = np.arange(1, len(ap) + 1)
    ap["country_code"] = "ZA"
    ap["has_fuel_farm"] = True
    ap["annual_uplift_band"] = rng.choice(["Large", "Medium", "Small"], len(ap))

    airline = pd.DataFrame({
        "airline_code": [f"SY{i:02d}" for i in range(1, 19)],
        "airline_key": np.arange(1, 19),
        "airline_name": names.AIRLINE_NAMES[:18],
        "airline_type": rng.choice(["Full Service", "Low Cost", "Cargo", "Charter"], 18),
        "is_contracted": rng.random(18) < 0.7,
    })

    port = pd.DataFrame(geo.SA_PORTS,
                        columns=["port_code", "port_name", "province", "city"])
    port["port_key"] = np.arange(1, len(port) + 1)
    port["country_code"] = "ZA"
    port["has_bunkering"] = rng.random(len(port)) < 0.75

    n_ves = max(40, int(600 * profile.secondary_scale) + 40)
    vessel = pd.DataFrame({
        "vessel_imo": [f"IMO{9000000 + i}" for i in range(1, n_ves + 1)],
        "vessel_key": np.arange(1, n_ves + 1),
        "vessel_name": names.vessel_names(rng, n_ves),
        "vessel_class": rng.choice(
            ["Container", "Bulk Carrier", "Tanker", "Fishing", "Naval", "Offshore"],
            n_ves),
        "deadweight_tonnes": rng.integers(1_200, 320_000, n_ves),
        "flag_country_code": rng.choice([m[0] for m in geo.MARKETS], n_ves),
    })
    return {"dim_airport": ap, "dim_airline": airline,
            "dim_port": port, "dim_vessel": vessel}


# ==========================================================================
# Bridges
# ==========================================================================
def build_bridges(rng, profile, dims: dict) -> dict[str, pd.DataFrame]:
    site = dims["dim_site"]
    product = dims["dim_product"]
    customer = dims["dim_customer"]
    contract = dims["dim_contract"]
    supplier = dims["dim_supplier"]
    route = dims["dim_route"]
    promo = dims["dim_promotion"]
    employee = dims["dim_employee"]
    asset = dims["dim_asset"]

    def pairs(left_ids, right_ids, avg_per_left, cols, cap=None):
        counts = rng.poisson(avg_per_left, len(left_ids)).clip(1, None)
        if cap:
            counts = counts.clip(None, cap)
        left = np.repeat(left_ids, counts)
        right = rng.choice(right_ids, len(left))
        return pd.DataFrame({cols[0]: left, cols[1]: right})

    sp = pairs(site["site_id"].to_numpy(),
               product["product_id"].to_numpy(), 6, ["site_id", "product_id"], 14)
    sp["is_primary_grade"] = rng.random(len(sp)) < 0.30
    sp["listed_from_date"] = pd.Timestamp(config.DATE_START)

    cc = pairs(customer["customer_id"].to_numpy(),
               contract["contract_id"].to_numpy(), 1.2,
               ["customer_id", "contract_id"], 5)
    cc["is_primary_contract"] = rng.random(len(cc)) < 0.6

    cs = pairs(customer["customer_id"].to_numpy()[: max(1, len(customer) // 4)],
               site["site_id"].to_numpy(), 2.0, ["customer_id", "site_id"], 12)
    cs["delivery_point_flag"] = rng.random(len(cs)) < 0.5

    sprm = pairs(site["site_id"].to_numpy(),
                 promo["promotion_id"].to_numpy(), 1.5,
                 ["site_id", "promotion_id"], 6)
    sprm["participation_flag"] = rng.random(len(sprm)) < 0.85

    es = pairs(employee["employee_id"].to_numpy(),
               site["site_id"].to_numpy(), 1.1, ["employee_id", "site_id"], 4)
    es["is_home_site"] = rng.random(len(es)) < 0.7

    asite = asset[["asset_id", "site_id"]].copy()
    asite["assigned_from_date"] = pd.Timestamp(config.DATE_START)

    supp = pairs(supplier["supplier_id"].to_numpy(),
                 product["product_id"].to_numpy(), 3.0,
                 ["supplier_id", "product_id"], 10)
    supp["is_approved"] = rng.random(len(supp)) < 0.9

    rs = pairs(route["route_id"].to_numpy(),
               site["site_id"].to_numpy(), 3.0, ["route_id", "site_id"], 9)
    rs["drop_sequence"] = rng.integers(1, 9, len(rs))

    # Ragged customer hierarchy: a subset of customers roll up to a parent.
    n_par = max(1, len(customer) // 20)
    parents = customer["customer_id"].to_numpy()[:n_par]
    ch = pd.DataFrame({
        "parent_customer_id": rng.choice(parents, len(customer)),
        "child_customer_id": customer["customer_id"].to_numpy(),
    })
    ch["hierarchy_level"] = rng.integers(1, 4, len(ch))
    ch["ownership_pct"] = 1.0

    ph = product[["product_id", "category", "subcategory"]].copy()
    ph.columns = ["product_id", "level_1_category", "level_2_subcategory"]
    ph["level_3_product"] = product["product_name"].to_numpy()

    sh = site[["site_id", "country_code", "province", "city"]].copy()
    sh["region_level"] = np.where(sh["country_code"] == "ZA", "South Africa", "International")

    # Row-level security scope: which synthetic user sees which province.
    users = [f"synthetic.user{i:03d}@example.invalid" for i in range(1, 41)]
    scope_rows = []
    for u in users:
        provs = rng.choice(geo.SA_PROVINCES, rng.integers(1, 4), replace=False)
        for p in provs:
            scope_rows.append((u, "province", p))
    for u in users[:6]:
        scope_rows.append((u, "all", "ALL"))
    sec = pd.DataFrame(scope_rows, columns=["user_principal", "scope_type", "scope_value"])

    return {
        "bridge_site_product": sp, "bridge_customer_contract": cc,
        "bridge_customer_site": cs, "bridge_site_promotion": sprm,
        "bridge_employee_site": es, "bridge_asset_site": asite,
        "bridge_supplier_product": supp, "bridge_route_site": rs,
        "bridge_customer_hierarchy": ch, "bridge_product_hierarchy": ph,
        "bridge_site_hierarchy": sh, "bridge_security_user_scope": sec,
    }


# ==========================================================================
# Orchestration
# ==========================================================================
SCD2_DIMENSIONS = {"dim_site", "dim_customer", "dim_product", "dim_supplier",
                   "dim_employee", "dim_contract"}


def build_all(rng, profile: config.ScaleProfile, writer: LakeWriter,
              injector=None) -> DimContext:
    """Build and persist every dimension, returning the fact-generation context."""
    geo.validate()
    dims: dict[str, pd.DataFrame] = {}

    dims["dim_date"] = build_dim_date()
    dims["dim_time"] = build_dim_time()
    dims.update(build_geography_dims(rng))

    site = build_dim_site(rng, profile)
    dims["dim_site"] = site
    terminal = build_dim_terminal(rng, profile)
    dims["dim_terminal"] = terminal
    depot = build_dim_depot(rng, profile, terminal)
    dims["dim_depot"] = depot
    dims["dim_warehouse"] = build_dim_warehouse(rng, profile, depot)

    dims.update(build_product_dims(rng))

    customer = build_dim_customer(rng, profile)
    dims["dim_customer"] = customer
    dims["dim_supplier"] = build_dim_supplier(rng, profile)
    dims["dim_employee"] = build_dim_employee(rng, profile, site)

    dims.update(build_asset_dims(rng, profile, site))
    dims.update(build_logistics_dims(rng, profile, site, terminal))
    dims.update(build_commercial_dims(rng, profile, customer))
    dims.update(build_digital_dims(rng, profile, site))
    dims.update(build_finance_dims(rng, profile))
    dims.update(build_operational_code_dims(rng, profile))
    dims.update(build_transport_node_dims(rng, profile))

    bridges = build_bridges(rng, profile, dims)

    for name, df in dims.items():
        if name in SCD2_DIMENSIONS:
            df = _scd2_columns(df, rng, config.DATE_START)
            dims[name] = df
        # The DimContext below keeps the clean frame: fact generation must join
        # on real keys. Only the persisted landing-zone copy is damaged, which
        # is what the cleansing layer is measured against.
        types = logical_types(df)
        writer.write_dimension(
            name, injector.apply_dimension(name, df) if injector else df, types)
    for name, df in bridges.items():
        types = logical_types(df)
        writer.write_dimension(
            name, injector.apply_dimension(name, df) if injector else df, types)

    return DimContext(
        site=dims["dim_site"], product=dims["dim_product"],
        customer=dims["dim_customer"], supplier=dims["dim_supplier"],
        terminal=dims["dim_terminal"], depot=dims["dim_depot"],
        vehicle=dims["dim_vehicle"], driver=dims["dim_driver"],
        employee=dims["dim_employee"], asset=dims["dim_asset"],
        tank=dims["dim_tank"], pump=dims["dim_pump"],
        loyalty=dims["dim_loyalty_member"], digital_user=dims["dim_digital_user"],
        ev_charger=dims["dim_ev_charger"], solar_asset=dims["dim_solar_asset"],
        contract=dims["dim_contract"], route=dims["dim_route"],
        airport=dims["dim_airport"], port=dims["dim_port"],
        date_dim=dims["dim_date"], gl_account=dims["dim_gl_account"],
        cost_centre=dims["dim_cost_centre"], campaign=dims["dim_campaign"],
    )
