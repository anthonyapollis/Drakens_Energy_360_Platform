"""Predict late primary-distribution deliveries.

Business question: which of tomorrow's planned deliveries will miss its slot,
so the schedule can be adjusted while there is still time.

Grain: one row per delivery, from `fct_deliveries`.

Only pre-departure information is used. `actual_arrival_ts` and
`delay_minutes` are the outcome; `fill_rate_pct` is measured on discharge.
Including any of them would produce a model that predicts the past.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    load,
    log_common_tags,
    log_sklearn_model,
    start_experiment,
    summarise,
    time_split,
)

QUERY = """
select
    d.delivery_id,
    d.planned_arrival_ts,
    d.date_key,
    d.route_id,
    d.origin_terminal_id,
    d.destination_site_id,
    d.vehicle_id,
    d.carrier_id,
    d.product_name,
    d.province,
    d.urban_class,
    d.planned_litres,
    d.distance_km,
    d.drop_count,
    d.is_on_time,
    dd.day_of_week,
    dd.month_number,
    dd.is_weekend,
    dd.is_public_holiday_za,
    dd.season_southern
from main_gold.fct_deliveries d
join main_gold.dim_date dd on d.date_key = dd.date_key
where d.distance_km is not null
"""

NUMERIC = ["planned_litres", "distance_km", "drop_count", "km_per_drop",
           "planned_hour", "day_of_week", "month_number",
           "carrier_late_rate_to_date", "route_late_rate_to_date"]
CATEGORICAL = ["product_name", "province", "urban_class", "season_southern"]


def build_features(df):
    df = df.sort_values("planned_arrival_ts").copy()

    # A delivery whose punctuality is unknown cannot be labelled. Treating it
    # as on-time would bias the model toward optimism, which is the wrong
    # direction for a late-delivery alert.
    before = len(df)
    df = df.dropna(subset=["is_on_time"])
    if before != len(df):
        print(f"dropped {before - len(df):,} deliveries with unknown punctuality")

    df["is_late"] = (~df["is_on_time"].astype(bool)).astype("int8")
    df["planned_hour"] = df["planned_arrival_ts"].dt.hour
    df["km_per_drop"] = df["distance_km"] / df["drop_count"].clip(lower=1)
    for flag in ("is_weekend", "is_public_holiday_za"):
        df[flag] = df[flag].fillna(False).astype("int8")

    # A carrier's own track record is the single most useful predictor, but it
    # has to be computed from prior deliveries only. An expanding mean shifted
    # by one row does that; a plain group mean would leak the outcome.
    for entity, name in (("carrier_id", "carrier"), ("route_id", "route")):
        df[f"{name}_late_rate_to_date"] = (
            df.groupby(entity, observed=True)["is_late"]
            .apply(lambda s: s.shift(1).expanding().mean())
            .reset_index(level=0, drop=True)
        )
    overall = df["is_late"].mean()
    return df.fillna({"carrier_late_rate_to_date": overall,
                      "route_late_rate_to_date": overall})


def main() -> int:
    start_experiment("late_delivery")
    raw = load(QUERY)
    print(f"loaded {len(raw):,} deliveries")

    df = build_features(raw)
    print(f"late rate: {df.is_late.mean():.1%}")

    train, test = time_split(df, "planned_arrival_ts", holdout_frac=0.25)
    cols = NUMERIC + CATEGORICAL + ["is_weekend", "is_public_holiday_za"]
    X_train, y_train = train[cols], train["is_late"]
    X_test, y_test = test[cols], test["is_late"]

    params = dict(max_iter=300, learning_rate=0.07, max_depth=6,
                  min_samples_leaf=40, random_state=42)

    with mlflow.start_run(run_name="hgbc_late_delivery"):
        log_common_tags("late_delivery", "delivery", "is_late")
        mlflow.log_params(params)
        mlflow.log_param("features_are_pre_departure_only", True)
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
        for k in (10, 20):
            n = max(1, int(len(proba) * k / 100))
            top = np.argsort(-proba)[:n]
            metrics[f"precision_at_top_{k}pct"] = float(y_test.iloc[top].mean())
            metrics[f"lift_at_top_{k}pct"] = float(
                y_test.iloc[top].mean() / max(y_test.mean(), 1e-9))
        mlflow.log_metrics(metrics)
        log_sklearn_model(pipeline)

        summarise("Late delivery risk", metrics)
        print("\n" + classification_report(
            y_test, (proba > 0.5).astype(int),
            target_names=["on time", "late"], digits=3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
