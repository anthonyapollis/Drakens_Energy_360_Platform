"""Detect anomalous forecourt activity.

Business question: which site-shifts look wrong -- pump meter readings that do
not reconcile to sales, cash variances, or refuelling patterns that suggest
fuel is leaving without being paid for.

Grain: one row per site per shift.

This is unsupervised on purpose. There is no labelled fraud in the data, and
in a real downstream business there rarely is: what exists is a stream of
plausible-looking transactions and an investigations team with finite
capacity. So the model ranks by unusualness and the output is a worklist, not
a verdict. Isolation Forest is used because it needs no labels and handles
the mixed-scale features here without much tuning.

An important honesty point, recorded in the run tags: a high anomaly score
means "unlike the rest of the population", not "fraudulent". Most of what
surfaces will be a miscalibrated meter or a badly closed shift, and that is
still worth finding.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import RobustScaler

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import load, log_common_tags, start_experiment, summarise  # noqa: E402

QUERY = """
with shift_sales as (
    select
        site_id,
        date_key,
        shift_name,
        count(*)                    as transaction_count,
        sum(litres)                 as litres_sold,
        sum(gross_sales_zar)        as sales_zar,
        sum(case when payment_method = 'Cash'
                 then gross_sales_zar else 0 end) as cash_sales_zar,
        avg(litres)                 as avg_fill_litres,
        max(litres)                 as max_fill_litres,
        count(distinct pump_number) as pumps_used,
        avg(unit_price_zar)         as avg_price_zar
    from main_gold.fct_retail_fuel_sales
    where site_id is not null
    group by 1, 2, 3
)
select
    s.*,
    d.is_weekend,
    d.is_public_holiday_za,
    site.province,
    site.urban_class,
    site.demand_band
from shift_sales s
join main_gold.dim_date d on s.date_key = d.date_key
join main_gold.dim_site site on s.site_id = site.site_id and site.is_current
"""

FEATURES = [
    "transaction_count", "litres_sold", "sales_zar",
    "avg_fill_litres", "max_fill_litres", "pumps_used",
    "cash_share", "litres_per_transaction", "revenue_per_litre",
    "max_to_avg_fill_ratio", "litres_vs_site_median",
    "transactions_vs_site_median",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["cash_share"] = df.cash_sales_zar / df.sales_zar.replace(0, np.nan)
    df["litres_per_transaction"] = (
        df.litres_sold / df.transaction_count.replace(0, np.nan))
    df["revenue_per_litre"] = df.sales_zar / df.litres_sold.replace(0, np.nan)
    # A single very large fill against a normal average is the shape that
    # matters most: one tanker-sized transaction hidden in a retail shift.
    df["max_to_avg_fill_ratio"] = (
        df.max_fill_litres / df.avg_fill_litres.replace(0, np.nan))

    # Compare each shift against that site's own normal, not the network's.
    # A quiet rural site and a Gauteng truck stop have nothing in common, and
    # scoring them on the same absolute scale would flag every large site.
    g = df.groupby("site_id", observed=True)
    df["litres_vs_site_median"] = (
        df.litres_sold / g["litres_sold"].transform("median").replace(0, np.nan))
    df["transactions_vs_site_median"] = (
        df.transaction_count
        / g["transaction_count"].transform("median").replace(0, np.nan))
    return df.replace([np.inf, -np.inf], np.nan).dropna(subset=FEATURES)


def main() -> int:
    start_experiment("fraud_anomaly")
    raw = load(QUERY)
    print(f"loaded {len(raw):,} site-shifts")

    df = build_features(raw)
    print(f"scoring {len(df):,} shifts on {len(FEATURES)} features")

    contamination = 0.01     # investigations capacity, not a belief about fraud
    params = dict(n_estimators=300, max_samples="auto",
                  contamination=contamination, random_state=42, n_jobs=-1)

    with mlflow.start_run(run_name="isolation_forest_forecourt_anomaly"):
        log_common_tags("fraud_anomaly", "site x shift", "unsupervised")
        mlflow.set_tag(
            "interpretation",
            "A high score means unusual relative to the site's own history, "
            "not proven fraud. Output is an investigation worklist.")
        mlflow.log_params(params)
        mlflow.log_param("n_features", len(FEATURES))
        mlflow.log_param("rows_scored", len(df))

        X = RobustScaler().fit_transform(df[FEATURES])
        model = IsolationForest(**params)
        model.fit(X)

        df["anomaly_score"] = -model.score_samples(X)   # higher = stranger
        df["is_anomaly"] = model.predict(X) == -1

        flagged = df[df.is_anomaly]
        metrics = {
            "rows_scored": float(len(df)),
            "flagged_count": float(len(flagged)),
            "flagged_pct": float(len(flagged) / len(df) * 100),
            "score_mean": float(df.anomaly_score.mean()),
            "score_p99": float(df.anomaly_score.quantile(0.99)),
            # What the flagged population looks like, so a reviewer can judge
            # whether the model is finding anything interesting at all.
            "flagged_avg_cash_share": float(flagged.cash_share.mean()),
            "normal_avg_cash_share": float(df[~df.is_anomaly].cash_share.mean()),
            "flagged_avg_max_fill_ratio": float(flagged.max_to_avg_fill_ratio.mean()),
            "normal_avg_max_fill_ratio": float(
                df[~df.is_anomaly].max_to_avg_fill_ratio.mean()),
            "value_flagged_zar": float(flagged.sales_zar.sum()),
        }
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(model, name="model")

        summarise("Forecourt anomaly detection", metrics)
        print("\nTop 10 shifts by anomaly score:")
        cols = ["site_id", "date_key", "shift_name", "litres_sold",
                "sales_zar", "cash_share", "max_to_avg_fill_ratio",
                "anomaly_score"]
        print(df.nlargest(10, "anomaly_score")[cols].to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
