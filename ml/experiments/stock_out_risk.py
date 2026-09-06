"""Predict site stock-out risk.

Business question: which sites will run dry, early enough to bring a delivery
forward. A dry pump loses the sale and the customer visit; an emergency
delivery costs a premium. The model exists to trade one against the other.

Grain: one row per inventory snapshot, from `fct_inventory_position`.

The stock-out definition comes from the mart (`is_stock_out_risk`, driven by
the `stock_out_cover_days` project variable), not from a threshold invented
here -- so the alert on the dashboard and the model's target are the same
thing by construction.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (average_precision_score, classification_report,
                             precision_recall_curve, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import load, log_common_tags, start_experiment, summarise, time_split  # noqa: E402

QUERY = """
select
    i.snapshot_ts,
    i.date_key,
    i.site_id,
    i.product_id,
    i.fuel_grade,
    i.province,
    i.demand_band,
    i.location_type,
    i.capacity_litres,
    i.stock_on_hand_litres,
    i.ullage_litres,
    i.fill_pct,
    i.average_daily_usage_litres,
    i.days_of_cover,
    i.reorder_point_litres,
    i.is_stock_out_risk,
    d.day_of_week,
    d.month_number,
    d.is_weekend,
    d.is_public_holiday_za
from main_gold.fct_inventory_position i
join main_gold.dim_date d on i.date_key = d.date_key
where i.capacity_litres > 0
"""

NUMERIC = ["capacity_litres", "stock_on_hand_litres", "ullage_litres",
           "fill_pct", "average_daily_usage_litres", "reorder_point_litres",
           "usage_to_capacity_ratio", "headroom_above_reorder",
           "day_of_week", "month_number"]
CATEGORICAL = ["fuel_grade", "province", "demand_band", "location_type"]


def main() -> int:
    start_experiment("stock_out_risk")
    df = load(QUERY)
    print(f"loaded {len(df):,} inventory snapshots")
    print(f"stock-out risk base rate: {df.is_stock_out_risk.mean():.1%}")

    # `days_of_cover` is excluded on purpose: the target is derived from it, so
    # including it would let the model reproduce the definition rather than
    # learn anything about the drivers, and would score near-perfectly while
    # being worthless the moment the threshold changes.
    df["usage_to_capacity_ratio"] = (
        df["average_daily_usage_litres"] / df["capacity_litres"])
    df["headroom_above_reorder"] = (
        df["stock_on_hand_litres"] - df["reorder_point_litres"])
    df["is_weekend"] = df["is_weekend"].astype(int)
    df["is_public_holiday_za"] = df["is_public_holiday_za"].astype(int)

    train, test = time_split(df, "snapshot_ts", holdout_frac=0.25)
    cols = NUMERIC + CATEGORICAL + ["is_weekend", "is_public_holiday_za"]
    X_train, y_train = train[cols], train["is_stock_out_risk"].astype(int)
    X_test, y_test = test[cols], test["is_stock_out_risk"].astype(int)

    params = dict(max_iter=300, learning_rate=0.08, max_depth=7,
                  min_samples_leaf=40, random_state=42)

    with mlflow.start_run(run_name="hgbc_stock_out_risk"):
        log_common_tags("stock_out_risk", "location x product x snapshot",
                        "is_stock_out_risk")
        mlflow.log_params(params)
        mlflow.log_param("excluded_leaky_feature", "days_of_cover")
        mlflow.log_param("train_rows", len(train))

        pipeline = Pipeline([
            ("encode", ColumnTransformer(
                [("cat", OrdinalEncoder(handle_unknown="use_encoded_value",
                                        unknown_value=-1), CATEGORICAL)],
                remainder="passthrough")),
            ("model", HistGradientBoostingClassifier(**params)),
        ])
        pipeline.fit(X_train, y_train)
        proba = pipeline.predict_proba(X_test)[:, 1]

        metrics = {
            "roc_auc": roc_auc_score(y_test, proba),
            "average_precision": average_precision_score(y_test, proba),
            "base_rate": float(y_test.mean()),
        }

        # Choose the operating threshold from the cost asymmetry, not from the
        # 0.5 default. Missing a stock-out is roughly four times worse than an
        # unnecessary early delivery, so recall is weighted accordingly.
        precision, recall, thresholds = precision_recall_curve(y_test, proba)
        beta = 2.0
        f_beta = ((1 + beta**2) * precision * recall
                  / np.maximum(beta**2 * precision + recall, 1e-9))
        best = int(np.nanargmax(f_beta[:-1])) if len(thresholds) else 0
        threshold = float(thresholds[best]) if len(thresholds) else 0.5
        metrics["operating_threshold"] = threshold
        metrics["precision_at_threshold"] = float(precision[best])
        metrics["recall_at_threshold"] = float(recall[best])

        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(pipeline, name="model")

        summarise("Stock-out risk", metrics)
        print("\n" + classification_report(
            y_test, (proba > threshold).astype(int),
            target_names=["healthy", "at risk"], digits=3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
