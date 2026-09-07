"""Unit tests for the synthetic data generator.

These run in CI on the `test` profile, which builds about 1.9 million fact
rows in roughly a minute. The point is not to test pandas; it is to catch the
specific ways this generator can silently produce data that looks fine and is
wrong -- a province quietly dropped, a coordinate outside the country, a
demand curve that flattens out, or a ledger that stops balancing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from drakens360 import config, dimensions, dirty, geography, names, reference
from drakens360.facts import _common as fc
from drakens360.writer import LakeWriter


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------
@pytest.fixture(scope="module")
def rng():
    return np.random.default_rng(config.DEFAULT_SEED)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """One dev-scale build shared across the module."""
    out = tmp_path_factory.mktemp("lake")
    writer = LakeWriter(out / "lake")
    generator = np.random.default_rng(config.DEFAULT_SEED)
    injector = dirty.DefectInjector(dirty.CLEAN, np.random.default_rng(1))
    ctx = dimensions.build_all(generator, config.DEV, writer, injector)
    return ctx, writer


# --------------------------------------------------------------------------
# Geography: the contractual requirements
# --------------------------------------------------------------------------
def test_all_nine_provinces_present():
    geography.validate()
    covered = {a.province for a in geography.SA_ANCHORS}
    assert covered == set(geography.SA_PROVINCES)
    assert len(geography.SA_PROVINCES) == 9


def test_anchors_inside_south_africa():
    for a in geography.SA_ANCHORS:
        assert -35.0 <= a.latitude <= -22.0, f"{a.city} latitude out of range"
        assert 16.0 <= a.longitude <= 33.5, f"{a.city} longitude out of range"


def test_portfolio_site_count_matches_public_order_of_magnitude():
    # The spec calls for roughly 1,050 South African sites.
    assert config.PORTFOLIO.sites_za == 1_050


def test_every_province_receives_sites(built):
    ctx, _ = built
    za = ctx.site[ctx.site.country_code == "ZA"]
    assert set(za.province.dropna()) == set(geography.SA_PROVINCES), (
        "a province received no sites; the anchor weights have drifted")


def test_site_coordinates_are_jittered_not_centroids(built):
    """No generated site may sit exactly on a town centroid.

    An exact match would imply the coordinate is a real location rather than
    a synthetic one, which is the claim the disclaimer explicitly denies.
    """
    ctx, _ = built
    centroids = {(round(a.latitude, 4), round(a.longitude, 4))
                 for a in geography.SA_ANCHORS}
    za = ctx.site[ctx.site.country_code == "ZA"]
    exact = [(round(r.latitude, 4), round(r.longitude, 4)) in centroids
             for r in za.itertuples()]
    assert not any(exact), "a synthetic site landed exactly on a town centroid"


# --------------------------------------------------------------------------
# Model shape
# --------------------------------------------------------------------------
def test_model_has_seventy_dimensions_and_twelve_bridges(built):
    _, writer = built
    dims = [k for k in writer.stats if k.startswith("dim_")]
    bridges = [k for k in writer.stats if k.startswith("bridge_")]
    assert len(dims) == 70, f"expected 70 dimensions, found {len(dims)}"
    assert len(bridges) == 12, f"expected 12 bridges, found {len(bridges)}"


def test_every_planned_fact_has_a_generator():
    from drakens360 import facts
    registry = facts.load_all()
    planned = config.planned_fact_rows(config.PORTFOLIO)
    missing = sorted(set(planned) - set(registry))
    assert not missing, f"fact tables with no generator: {missing}"
    assert len(planned) == 85


def test_portfolio_profile_exceeds_the_row_floor():
    plan = config.planned_fact_rows(config.PORTFOLIO)
    total = sum(plan.values())
    assert total >= config.MIN_PORTFOLIO_FACT_ROWS, (
        f"portfolio plans {total:,} fact rows, below the "
        f"{config.MIN_PORTFOLIO_FACT_ROWS:,} floor")


# --------------------------------------------------------------------------
# Demand shape: the reason the data is worth modelling on
# --------------------------------------------------------------------------
def test_hourly_demand_has_commute_peaks(rng):
    ts = fc.sample_timestamps(rng, 200_000)
    by_hour = ts.dt.hour.value_counts().sort_index()
    # Morning and evening peaks must clearly exceed the small hours, or the
    # forecasting model has nothing to learn.
    quiet = by_hour.loc[[2, 3, 4]].mean()
    morning = by_hour.loc[[7, 8]].mean()
    evening = by_hour.loc[[16, 17, 18]].mean()
    assert morning > quiet * 4, "no morning commute peak in the demand curve"
    assert evening > quiet * 4, "no evening peak in the demand curve"


def test_weekday_shape_is_not_flat(rng):
    ts = fc.sample_timestamps(rng, 200_000)
    by_dow = ts.dt.dayofweek.value_counts(normalize=True)
    # Friday (4) should beat Sunday (6) by a clear margin.
    assert by_dow[4] > by_dow[6] * 1.25, "weekday demand shape is flat"


def test_fuel_price_moves_in_monthly_steps(rng):
    """Regulated prices step once a month; they do not wander per transaction."""
    ts = fc.sample_timestamps(rng, 20_000)
    price = fc.price_path(ts, 24.10, rng, len(ts))
    df = pd.DataFrame({"month": ts.dt.to_period("M").astype(str), "price": price})
    # Within a month the only variation is the small zone differential, so the
    # spread inside a month must be far tighter than the spread across months.
    within = df.groupby("month")["price"].std().mean()
    across = df.groupby("month")["price"].mean().std()
    assert across > within, (
        "prices vary more within a month than between months, which means the "
        "monthly step function is not being applied")


def test_site_demand_index_is_heterogeneous(built):
    ctx, _ = built
    d = ctx.site.demand_index
    assert d.max() / d.median() > 2.0, (
        "every site trades at the same rate; the demand index is not working")


# --------------------------------------------------------------------------
# Referential integrity of the clean generator output
# --------------------------------------------------------------------------
def test_asset_failure_propensity_rises_with_age(built):
    ctx, _ = built
    a = ctx.asset
    young = a[a.age_years < 5].failure_propensity.mean()
    old = a[a.age_years > 15].failure_propensity.mean()
    assert old > young * 1.5, (
        "old assets are not modelled as more failure-prone, so the "
        "predictive-maintenance model has no signal to find")


def test_dimension_keys_are_unique(built):
    ctx, _ = built
    for name, df, key in [
        ("site", ctx.site, "site_id"),
        ("customer", ctx.customer, "customer_id"),
        ("product", ctx.product, "product_id"),
        ("supplier", ctx.supplier, "supplier_id"),
        ("terminal", ctx.terminal, "terminal_id"),
        ("vehicle", ctx.vehicle, "vehicle_id"),
        ("asset", ctx.asset, "asset_id"),
    ]:
        assert df[key].is_unique, f"{name}: duplicate {key}"
        assert df[key].notna().all(), f"{name}: null {key}"


# --------------------------------------------------------------------------
# Naming: no real organisation, and no placeholder strings
# --------------------------------------------------------------------------
def test_names_are_not_placeholders(built):
    ctx, _ = built
    for df, col in [(ctx.customer, "customer_name"),
                    (ctx.supplier, "supplier_name"),
                    (ctx.employee, "employee_name"),
                    (ctx.site, "site_name")]:
        sample = df[col].astype(str)
        assert not sample.str.startswith("Synthetic ").any(), (
            f"{col} still contains placeholder names")


def test_person_names_span_multiple_traditions(rng):
    generated = set(names.person_names(rng, 4_000))
    surnames = {n.split(" ", 1)[1] for n in generated}
    # A generator drawing only Anglophone names would produce a customer book
    # that looks nothing like South Africa.
    for expected in ("Dlamini", "van der Merwe", "Naidoo", "Molefe"):
        assert any(expected in s for s in surnames), (
            f"no {expected!r}-style surnames generated")


def test_site_names_are_unique_within_the_network(built):
    ctx, _ = built
    za = ctx.site[ctx.site.country_code == "ZA"]
    assert za.site_name.is_unique, "two South African sites share a name"


# --------------------------------------------------------------------------
# Defect injection
# --------------------------------------------------------------------------
def test_clean_profile_injects_nothing():
    injector = dirty.DefectInjector(dirty.CLEAN, np.random.default_rng(1))
    df = pd.DataFrame({"site_id": ["S000001"] * 100,
                       "litres": np.arange(100, dtype=float)})
    out = injector.apply("fact_retail_fuel_sales", df)
    pd.testing.assert_frame_equal(df, out)
    assert injector.summary()["total_defects_injected"] == 0


def test_realistic_profile_preserves_row_count():
    """Damage must never change how many rows landed.

    The cleansing layer is measured by reconciling raw against cleansed plus
    quarantined plus duplicates; if injection changed the row count, that
    reconciliation could never balance.
    """
    injector = dirty.DefectInjector(dirty.REALISTIC, np.random.default_rng(2))
    df = pd.DataFrame({
        "transaction_id": [f"RF{i:012d}" for i in range(5_000)],
        "site_id": ["S000001"] * 5_000,
        "product_id": ["F003"] * 5_000,
        "litres": np.random.default_rng(3).uniform(10, 80, 5_000),
        "transaction_ts": pd.Series(
            pd.date_range("2025-01-01", periods=5_000, freq="min")),
    })
    out = injector.apply("fact_retail_fuel_sales", df)
    assert len(out) == len(df)


def test_realistic_profile_actually_damages_data():
    injector = dirty.DefectInjector(dirty.REALISTIC, np.random.default_rng(4))
    df = pd.DataFrame({
        "transaction_id": [f"RF{i:012d}" for i in range(20_000)],
        "site_id": ["S000001"] * 20_000,
        "litres": np.random.default_rng(5).uniform(10, 80, 20_000),
        "transaction_ts": pd.Series(
            pd.date_range("2025-01-01", periods=20_000, freq="min")),
    })
    injector.apply("fact_retail_fuel_sales", df)
    summary = injector.summary()
    assert summary["total_defects_injected"] > 0
    # The flat-file feeds must deliver numbers as text, or the numeric-parsing
    # half of the cleansing layer is never exercised.
    assert "numeric_delivered_as_text" in summary["defects_by_type"]


def test_dimension_primary_keys_survive_injection():
    injector = dirty.DefectInjector(dirty.SEVERE, np.random.default_rng(6))
    df = pd.DataFrame({
        "site_id": [f"S{i:06d}" for i in range(2_000)],
        "site_name": ["Kalahari Fuels Cape Town"] * 2_000,
        "province": ["Western Cape"] * 2_000,
    })
    out = injector.apply_dimension("dim_site", df)
    assert out.site_id.equals(df.site_id), (
        "the dimension primary key was damaged, which would make referential "
        "integrity impossible to measure")


# --------------------------------------------------------------------------
# Reference data
# --------------------------------------------------------------------------
def test_product_prices_exceed_costs():
    for p in reference.PRODUCTS:
        if p.base_price_zar > 0:
            assert p.base_price_zar > p.base_cost_zar, (
                f"{p.product_id} would sell at a loss on every unit")


def test_regulated_fuels_are_thin_margin():
    """Regulated fuel must be materially thinner than unregulated lines.

    This is the central economic fact of the business being modelled: volume
    is regulated and thin, and the growth story is everything else. If the
    generator loses it, every margin-mix conclusion drawn from the data is
    wrong.
    """
    def margin(p):
        return (p.base_price_zar - p.base_cost_zar) / p.base_price_zar

    regulated = [margin(p) for p in reference.PRODUCTS
                 if p.regulated and p.base_price_zar > 0]
    shop = [margin(p) for p in reference.PRODUCTS
            if p.category == "Convenience" and p.base_price_zar > 0]
    assert np.mean(regulated) < np.mean(shop) / 2


def test_hour_and_weekday_weights_are_complete():
    assert len(reference.HOUR_WEIGHTS) == 24
    assert len(reference.DOW_WEIGHTS) == 7
    assert set(reference.MONTH_WEIGHTS) == set(range(1, 13))
