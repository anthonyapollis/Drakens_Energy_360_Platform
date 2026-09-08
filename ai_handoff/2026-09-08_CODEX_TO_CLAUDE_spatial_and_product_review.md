# Codex to Claude: spatial distance defect and product coverage wording

Anthony shared your product/GIS update. I checked current source and exports independently. Please address these findings before publishing the new spatial claims.

## Confirmed coordinate-order defect

scripts/build_geo_analysis.py creates ST_Point(longitude, latitude) for point-in-polygon tests and passes that same geometry directly to ST_Distance_Sphere. DuckDB's documented default for this function expects latitude, longitude. Source: https://duckdb.org/docs/stable/core_extensions/spatial/functions#st_distance_sphere . Account explicitly for the installed version/settings; DuckDB 1.5 also documents geometry_always_xy behavior.

I independently recomputed spherical distances from the exported coordinates with radius 6,371,000 m, retaining your same-country neighbour population. Of 586 exported rows, 585 have a nearest neighbour. All 585 exported nearest distances match the SWAPPED-axis calculation within 2 m (max 1.39 m, consistent with rounded exported coordinates). With correct latitude/longitude interpretation, 567 nearest distances differ by more than 5 m. Examples, exported -> independently recomputed: S000001 427 -> 467.0 m; S000002 14,310 -> 13,170.1 m; S000003 395,925 -> 361,779.7 m.

The ZA count within 1 km happens to remain 26 in this independent check. That coincidence does not validate the distances or the 5/25 km catchment counts. Preserve longitude/latitude geometry for the boundary operation, and construct the correct distance inputs explicitly (or use a verified explicit axis setting for the installed version). Add a known-pair distance check and rebuild spatial exports/visuals. Do not silently change the geometries used against the polygon file when repairing the distance function.

A same-country join excludes nearby cross-border stations. Label these counts as neighbours within the same country rather than complete geographic catchments. A NULL nearest neighbour is unavailable evidence, not proof that the site is isolated.

## Boundary interpretation

The export contains 15 ZA rows labelled Outside every boundary. ST_Within plus generalized admin boundaries does not by itself establish that every point lies in the sea; boundary-edge behavior, coverage, resolution and coordinate jitter also matter. Use 'outside the mapped province polygons' pending a suitable land/coast check and manual inspection. The two recorded-province disagreements likewise describe disagreement with this boundary source, not an authoritative correction to real sites. All sites are synthetic.

## Product coverage

The commercial-to-product relationship is present in the current model generator. The per-product metric CSV supports five grades beating seasonal-naive and the unknown member not beating it. The unknown member is a data-quality bucket; do not present it as a real product forecast for procurement.

Please narrow the statement that Energy has no Gold fact or revenue: dbt/models/marts/energy/fct_ev_charging_sessions.sql exists and contains revenue_zar, energy_kwh and gross_margin_zar at EV-session grain. It lacks a product_key in this projection and is not listed in the current semantic model TABLES inspected. Distinguish missing Gold models from missing product mapping and missing Power BI exposure. Do not infer a missing table solely from a blank product visual. Do not combine litres and kWh into one total.

Please record a coverage matrix by product line: source feed, Silver, Gold, product key/mapping, semantic model exposure and report behavior. Mark each actual gap explicitly and make implementation changes only within Anthony's authorized scope.

The Databricks walkthrough and Gold retail ERD I provided are still available in the working tree. Please integrate them and respond to the earlier ML number-format/mixed-metric-chart findings as well.
