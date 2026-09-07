"""Integration tests against the built warehouse.

These run after `dbt build` and check the things dbt's own tests cannot: that
the cleansing layer accounts for every row it was given, that the gold layer
agrees with the silver layer it was derived from, and that the business
invariants hold end to end.

Skipped automatically if the warehouse has not been built, so a developer
running `pytest` without a warehouse gets a clear skip rather than a wall of
errors.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import pytest

REPO = Path(__file__).resolve().parent.parent
DB = Path(os.environ.get("VIVO_DUCKDB_PATH", REPO / "data" / "vivo360.duckdb"))

pytestmark = pytest.mark.skipif(
    not DB.exists(),
    reason=f"warehouse not built at {DB}; run the generator and `dbt build` first",
)


@pytest.fixture(scope="module")
def con():
    try:
        c = duckdb.connect(str(DB), read_only=True)
    except duckdb.IOException as exc:
        # The file exists but cannot be opened -- almost always because a dbt
        # build is holding it. Skipping is right: erroring here produces a wall
        # of identical tracebacks that hides whatever else is failing.
        pytest.skip(f"warehouse at {DB} is not readable: {str(exc)[:120]}")
    yield c
    c.close()


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def table_exists(con, schema, table):
    return scalar(con, f"""
        select count(*) from information_schema.tables
        where table_schema = '{schema}' and table_name = '{table}'
    """) > 0


# --------------------------------------------------------------------------
# Cleansing reconciliation
# --------------------------------------------------------------------------
def test_every_landed_row_is_accounted_for(con):
    """raw = cleansed + quarantined + duplicates removed, for every feed.

    This is the single most important test in the suite. If it fails, rows
    are being lost somewhere in the cleansing layer, and a lost row becomes an
    unexplainable variance that nobody can trace back months later.
    """
    if not table_exists(con, "main_platform", "obs_cleansing_summary"):
        pytest.skip("obs_cleansing_summary not built")

    bad = con.execute("""
        select table_name, raw_rows, cleansed_rows, quarantined_rows,
               duplicates_removed
        from main_platform.obs_cleansing_summary
        where raw_rows <> cleansed_rows + quarantined_rows + duplicates_removed
    """).df()
    assert bad.empty, f"rows unaccounted for:\n{bad.to_string(index=False)}"


def test_no_negative_duplicate_counts(con):
    """A negative duplicate count means more rows came out than went in."""
    if not table_exists(con, "main_platform", "obs_cleansing_summary"):
        pytest.skip("obs_cleansing_summary not built")
    bad = con.execute("""
        select table_name, duplicates_removed
        from main_platform.obs_cleansing_summary
        where duplicates_removed < 0
    """).df()
    assert bad.empty, f"cleansing produced rows from nowhere:\n{bad}"


def test_quarantine_rate_is_plausible(con):
    """A feed rejecting more than a fifth of its rows is broken, not dirty."""
    if not table_exists(con, "main_platform", "obs_cleansing_summary"):
        pytest.skip("obs_cleansing_summary not built")
    bad = con.execute("""
        select table_name, quarantine_rate_pct
        from main_platform.obs_cleansing_summary
        where quarantine_rate_pct > 20
    """).df()
    assert bad.empty, f"implausible rejection rate:\n{bad.to_string(index=False)}"


def test_cleansed_rows_have_no_sentinel_values(con):
    """The sentinels the generator injected must not survive into silver."""
    remaining = scalar(con, """
        select count(*) from main_silver.stg_fact_retail_fuel_sales
        where site_id in ('NULL', 'N/A', '#N/A', '-', '?', 'UNKNOWN', 'NONE', '')
           or product_id in ('NULL', 'N/A', '#N/A', '-', '?', 'UNKNOWN', 'NONE', '')
    """)
    assert remaining == 0, f"{remaining:,} sentinel values survived cleansing"


def test_cleansed_codes_are_trimmed_and_upper_case(con):
    bad = scalar(con, """
        select count(*) from main_silver.stg_fact_retail_fuel_sales
        where site_id <> upper(trim(site_id))
    """)
    assert bad == 0, f"{bad:,} site codes still carry whitespace or lower case"


def test_numeric_columns_parsed_out_of_text(con):
    """Locale-formatted numbers must have become real numbers."""
    nulls = scalar(con, """
        select count(*) from main_silver.stg_fact_retail_fuel_sales
        where litres is null
    """)
    total = scalar(con, "select count(*) from main_silver.stg_fact_retail_fuel_sales")
    # Some nulls are expected (sentinels correctly stripped), but a large
    # proportion means the numeric parser is failing on a common format.
    assert nulls / max(total, 1) < 0.02, (
        f"{nulls:,} of {total:,} litres values failed to parse -- the locale "
        f"handling in clean_numeric is probably wrong")


def test_no_out_of_range_timestamps_survive(con):
    bad = scalar(con, """
        select count(*) from main_silver.stg_fact_retail_fuel_sales
        where transaction_ts < timestamp '2023-01-01'
           or transaction_ts > timestamp '2027-12-31'
    """)
    assert bad == 0, f"{bad:,} epoch or future timestamps survived cleansing"


# --------------------------------------------------------------------------
# Referential integrity in gold
# --------------------------------------------------------------------------
def test_no_orphan_site_keys_in_gold(con):
    orphans = scalar(con, """
        select count(*) from main_gold.fct_retail_fuel_sales f
        left join main_gold.dim_site s on f.site_key = s.site_key
        where s.site_key is null
    """)
    assert orphans == 0, f"{orphans:,} fact rows reference a missing site"


def test_no_orphan_date_keys_in_gold(con):
    orphans = scalar(con, """
        select count(*) from main_gold.fct_retail_fuel_sales f
        left join main_gold.dim_date d on f.date_key = d.date_key
        where d.date_key is null
    """)
    assert orphans == 0, f"{orphans:,} fact rows reference a missing date"


# --------------------------------------------------------------------------
# Business invariants
# --------------------------------------------------------------------------
def test_gross_margin_reconciles(con):
    """Margin must equal revenue less cost, to the cent."""
    bad = scalar(con, """
        select count(*) from main_gold.fct_retail_fuel_sales
        where abs(gross_margin_zar - (gross_sales_zar - cogs_zar)) > 0.02
    """)
    assert bad == 0, f"{bad:,} rows where margin does not reconcile"


def test_general_ledger_balances(con):
    """Double entry: total debits must equal total credits."""
    debits, credits = con.execute("""
        select sum(debit_amount_zar), sum(credit_amount_zar)
        from main_gold.fct_general_ledger
    """).fetchone()
    assert debits and credits
    variance = abs(debits - credits) / max(abs(debits), 1)
    assert variance < 0.0001, (
        f"ledger out of balance: debits {debits:,.2f} vs credits {credits:,.2f} "
        f"({variance:.2%} variance)")


def test_daily_aggregate_ties_to_transaction_fact(con):
    """The aggregate must be a faithful roll-up, not an approximation."""
    detail = scalar(con, "select sum(litres) from main_gold.fct_retail_fuel_sales")
    agg = scalar(con, "select sum(litres) from main_gold.agg_site_daily_fuel")
    variance = abs(detail - agg) / max(detail, 1)
    assert variance < 0.0001, (
        f"aggregate does not tie to detail: {detail:,.0f} vs {agg:,.0f}")


def test_all_reconciliation_controls_pass(con):
    if not table_exists(con, "main_platform", "obs_reconciliation_controls"):
        pytest.skip("obs_reconciliation_controls not built")
    failing = con.execute("""
        select control_code, expected_value, actual_value, variance_pct
        from main_platform.obs_reconciliation_controls
        where not is_passing
    """).df()
    assert failing.empty, (
        f"reconciliation controls failing:\n{failing.to_string(index=False)}")


# --------------------------------------------------------------------------
# Coverage and scale
# --------------------------------------------------------------------------
def test_all_nine_provinces_reach_gold(con):
    n = scalar(con, """
        select count(distinct province) from main_gold.dim_site
        where country_code = 'ZA' and province is not null
    """)
    assert n == 9, f"only {n} provinces present in the gold site dimension"


def test_south_african_site_count(con):
    n = scalar(con, """
        select count(*) from main_gold.dim_site
        where country_code = 'ZA' and is_current
    """)
    assert 1_000 <= n <= 1_100, (
        f"{n} South African sites; the spec calls for approximately 1,050")


def test_investment_scores_are_bounded(con):
    bad = scalar(con, """
        select count(*) from main_gold.network_investment_scorecard
        where investment_score < 0 or investment_score > 100
    """)
    assert bad == 0, f"{bad} sites scored outside 0-100"


def test_every_site_has_an_investment_recommendation(con):
    missing = scalar(con, """
        select count(*) from main_gold.network_investment_scorecard
        where investment_recommendation is null
    """)
    assert missing == 0, f"{missing} sites have no recommendation"


def test_solar_generates_nothing_at_night(con):
    """A physical impossibility check the cleansing layer must preserve."""
    if not table_exists(con, "main_silver", "stg_fact_solar_generation"):
        pytest.skip("solar staging not built")
    bad = scalar(con, """
        select count(*) from main_silver.stg_fact_solar_generation
        where not is_daylight and energy_kwh > 0
    """)
    assert bad == 0, f"{bad:,} solar readings generate power at night"
