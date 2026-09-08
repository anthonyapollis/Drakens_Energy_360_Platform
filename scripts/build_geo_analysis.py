"""Spatial analysis of the network, in SQL.

Three questions that cannot be answered without geometry, and that the rest of
the platform therefore never asks:

1. **Does each site's coordinate actually fall inside the province its record
   claims?** Every other data-quality check in this project compares a value
   against a rule or another column. This one compares a point against a
   polygon, and it is the only check capable of catching a site that is
   internally consistent and geographically wrong. The generator scatters
   sites around town centroids with 3-8 km of jitter, so sites near a
   provincial boundary genuinely can land on the wrong side -- and a network
   report grouped by province would attribute their margin to the wrong
   region without anything flagging it.

2. **How close is the nearest other site?** Two forecourts 800 m apart do not
   earn twice one forecourt. The investment engine ranks sites on their own
   performance and has no notion that a candidate's neighbour is across the
   road, which is exactly the sort of thing that makes a capital plan wrong in
   an expensive direction.

3. **How much of the network is within reach of each site?** Catchment counts
   at 5 km and 25 km separate a metro site competing with six others from a
   rural site that is the only fuel for an hour's drive. Those are different
   businesses and the same scorecard was ranking them together.

Distances are geodesic (`ST_Distance_Sphere`, metres). Planar distance on
lat/long degrees is wrong everywhere and most wrong at the latitudes this
network sits at.

Boundaries are Natural Earth 1:10m admin-1, public domain. Everything drawn on
them is generated: Drakens Energy is a fictional company and these coordinates
are town centroids plus random jitter, not real service stations.

Usage:
    python scripts/build_geo_analysis.py
    python scripts/build_geo_analysis.py --warehouse data/drakens360.duckdb
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parent.parent
PROVINCES_GPKG = REPO / "data" / "geo" / "za_provinces.gpkg"
OUT = REPO / "powerbi" / "data" / "obs_geo_site_analysis.csv"

# Natural Earth spells them as they are gazetted; the warehouse uses the
# common short forms. Mapped explicitly rather than fuzzy-matched, because a
# near-miss here silently reports every site in that province as misplaced.
PROVINCE_ALIASES = {
    "KwaZulu-Natal": "KwaZulu-Natal",
    "North West": "North West",
    "Northern Cape": "Northern Cape",
    "Western Cape": "Western Cape",
    "Eastern Cape": "Eastern Cape",
    "Free State": "Free State",
    "Gauteng": "Gauteng",
    "Limpopo": "Limpopo",
    "Mpumalanga": "Mpumalanga",
}

NEAR_M = 5_000
CATCHMENT_M = 25_000


def build(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("install spatial")
    con.execute("load spatial")

    if not PROVINCES_GPKG.exists():
        raise FileNotFoundError(
            f"{PROVINCES_GPKG} is missing; the point-in-polygon check cannot "
            f"run without boundaries")

    con.execute(f"""
        create or replace temp table province_geom as
        select name as province_boundary, geom
        from st_read('{PROVINCES_GPKG.as_posix()}')
    """)

    con.execute("""
        create or replace temp table site_pt as
        select
            site_key, site_id, site_name, country_code, province, city,
            urban_class, site_type, on_national_route, latitude, longitude,
            ST_Point(longitude, latitude) as geom
        from main_gold.dim_site
        where latitude is not null and longitude is not null
          and site_key <> -1
    """)

    # 1. Point in polygon. Only meaningful for South African sites: the
    #    boundaries are South African, and a site in Ghana is correctly
    #    outside all of them.
    con.execute("""
        create or replace temp table located as
        select
            s.*,
            (select p.province_boundary
             from province_geom p
             where ST_Within(s.geom, p.geom)
             limit 1) as boundary_province
        from site_pt s
    """)

    # 2 and 3. Nearest neighbour and catchment counts, geodesic.
    con.execute(f"""
        create or replace temp table neighbours as
        select
            a.site_key,
            min(ST_Distance_Sphere(a.geom, b.geom)) as nearest_site_m,
            count(*) filter (
                where ST_Distance_Sphere(a.geom, b.geom) <= {NEAR_M}
            ) as sites_within_5km,
            count(*) filter (
                where ST_Distance_Sphere(a.geom, b.geom) <= {CATCHMENT_M}
            ) as sites_within_25km
        from site_pt a
        join site_pt b
          on a.site_key <> b.site_key
         and a.country_code = b.country_code
        group by a.site_key
    """)

    con.execute(f"""
        create or replace temp table geo as
        select
            l.site_key,
            l.site_id,
            l.site_name,
            l.country_code,
            l.province                                  as recorded_province,
            l.boundary_province,
            l.city,
            l.urban_class,
            l.site_type,
            l.on_national_route,
            round(l.latitude, 5)                        as latitude,
            round(l.longitude, 5)                       as longitude,
            case
                when l.country_code <> 'ZA' then 'Not South Africa'
                when l.boundary_province is null then 'Outside every boundary'
                when l.province is null then 'No province recorded'
                when l.province = l.boundary_province then 'Matches'
                else 'Province mismatch'
            end                                         as province_check,
            round(n.nearest_site_m)                     as nearest_site_m,
            round(n.nearest_site_m / 1000.0, 2)         as nearest_site_km,
            coalesce(n.sites_within_5km, 0)             as sites_within_5km,
            coalesce(n.sites_within_25km, 0)            as sites_within_25km,
            case
                when n.nearest_site_m <= 1000 then 'Overlapping (under 1 km)'
                when n.nearest_site_m <= {NEAR_M} then 'Competing (under 5 km)'
                when n.nearest_site_m <= {CATCHMENT_M} then 'Clustered'
                else 'Isolated'
            end                                         as proximity_band,
            'Synthetic data. Drakens Energy is a fictional company. '
            'Coordinates are town centroids plus jitter.' as disclaimer
        from located l
        left join neighbours n on n.site_key = l.site_key
    """)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    con.execute(
        f"copy (select * from geo order by site_key) "
        f"to '{OUT.as_posix()}' (header, delimiter ',')")


def report(con: duckdb.DuckDBPyConnection) -> None:
    total = con.execute("select count(*) from geo").fetchone()[0]
    print(f"wrote {total:,} sites to {OUT.relative_to(REPO)}\n")

    print("point-in-polygon check:")
    for status, n in con.execute("""
        select province_check, count(*) from geo group by 1 order by 2 desc
    """).fetchall():
        print(f"  {status:26} {n:>5}")

    mismatched = con.execute("""
        select count(*) from geo where province_check = 'Province mismatch'
    """).fetchone()[0]
    if mismatched:
        print(f"\n  {mismatched} site(s) sit outside the province their record "
              f"claims:")
        for row in con.execute("""
            select site_name, recorded_province, boundary_province, city
            from geo where province_check = 'Province mismatch'
            order by site_name limit 12
        """).fetchall():
            print(f"    {row[0][:34]:34} recorded {row[1]:<15} "
                  f"actually {row[2]:<15} ({row[3]})")

    print("\nproximity:")
    for band, n, med in con.execute("""
        select proximity_band, count(*), round(median(nearest_site_km), 1)
        from geo group by 1
        order by min(nearest_site_m)
    """).fetchall():
        print(f"  {band:26} {n:>5} sites, median nearest {med} km")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--warehouse", default=os.environ.get(
        "DRAKENS_DUCKDB_PATH",
        str(REPO / "data" / "drakens360_test_full.duckdb")))
    args = ap.parse_args()

    path = Path(args.warehouse)
    if not path.exists():
        print(f"no warehouse at {path}")
        return 1
    try:
        con = duckdb.connect(str(path), read_only=True)
    except duckdb.IOException as exc:
        print(f"warehouse is locked: {str(exc)[:90]}")
        return 1
    try:
        build(con)
        report(con)
    finally:
        con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
