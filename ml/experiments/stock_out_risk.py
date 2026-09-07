"""Predict site stock-out risk.

Business question: which sites will run dry, early enough to bring a delivery
forward. A dry pump loses the sale and the customer visit; an emergency
delivery costs a premium. The model exists to trade one against the other.

Grain: one row per inventory snapshot, from `fct_inventory_position`.

The stock-out definition comes from the mart (`is_stock_out_risk`, driven by
the `stock_out_cover_days` project variable), not from a threshold invented
here -- so the alert on the dashboard and the model's target are the same
thing by construction.

**The target is the *next* snapshot, not the current one.** This matters more
than any hyperparameter in the file. Scored against the current snapshot the
model reaches ROC-AUC 0.998, which is not a result -- it is the definition
coming back out. `is_stock_out_risk` is `days_of_cover` below a threshold, and
`days_of_cover` is `stock_on_hand_litres` over `average_daily_usage_litres`.
Excluding `days_of_cover` from the features while leaving both of its
components in place excludes nothing: the model divides one by the other and
reproduces the rule exactly.

Predicting the next observed snapshot removes the leak, because the target is
then measured at a later timestamp than every feature. It also matches the
decision: nobody needs a model to tell them a tank is low right now -- the
gauge says so. What is worth knowing is which tank will be low at the next
look, while there is still time to move a delivery.

The snapshot cadence is irregular, so the realised horizon is measured and
logged rather than assumed.

**The honest result: at this cadence the model has no signal.** The median gap
between consecutive snapshots of the same tank is 84 days, and a tank's level
today says nothing about its level three months later -- it will have been
refilled and drawn down many times in between. ROC-AUC lands at 0.51.

Both numbers are true statements about the same data. Scored against the
current snapshot the model reaches 0.998 and is measuring its own definition;
scored against the next snapshot it reaches 0.51 and is measuring nothing.
The leaked version is the only learnable one, which is precisely why the leak
had to be found.

What would make this model exist is a denser inventory series -- daily tank
readings rather than roughly quarterly ones. The platform already streams tank
telemetry; wiring `fact_tank_telemetry` into this fact, instead of the sparse
`fct_inventory_position` snapshots, is the change that matters. It is a change
to the data, not to the estimator.
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
    precision_recall_curve,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    as_model_matrix,
    load,
    log_common_tags,
    log_sklearn_model,
    start_experiment,
    summarise,
    time_split,
)

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
           "days_of_cover", "horizon_days", "prior_stock_out_rate",
           "day_of_week", "month_number"]
CATEGORICAL = ["fuel_grade", "province", "demand_band", "location_type"]


def build_next_snapshot_target(df):
    """Shift the target forward to the next snapshot of the same tank.

    Grain is site x product, so the shift is taken within that group after
    sorting by time. The last snapshot of each tank has no successor and is
    dropped -- there is nothing to predict, and carrying it forward with its
    own label would put the leak straight back in.

    The realised horizon is kept as a feature: the gap between snapshots is
    irregular, and a stock-out is far likelier over sixty days than over five.
    A model that cannot see how far ahead it is being asked to look has to
    average over that, and it is information the planner has anyway.
    """
    df = df.sort_values(["site_id", "product_id", "snapshot_ts"]).copy()
    g = df.groupby(["site_id", "product_id"], observed=True)

    df["target_stock_out"] = g["is_stock_out_risk"].shift(-1)
    df["horizon_days"] = (
        g["snapshot_ts"].shift(-1) - df["snapshot_ts"]
    ).dt.total_seconds() / 86400.0

    # The tank's own history, from earlier snapshots only.
    df["prior_stock_out_rate"] = (
        g["is_stock_out_risk"]
        .apply(lambda x: x.shift(1).expanding().mean())
        .reset_index(level=[0, 1], drop=True)
    )

    before = len(df)
    df = df.dropna(subset=["target_stock_out", "horizon_days"])
    print(f"dropped {before - len(df):,} final snapshots with no successor")
    df["target_stock_out"] = df["target_stock_out"].astype(bool).astype("int8")
    return df.fillna({"prior_stock_out_rate": float(df["is_stock_out_risk"].mean())})


def main() -> int:
    start_experiment("stock_out_risk")
    df = load(QUERY)
    print(f"loaded {len(df):,} inventory snapshots")
    print(f"stock-out risk base rate, current snapshot: "
          f"{df.is_stock_out_risk.mean():.1%}")

    # A row whose state is unknown cannot be learned from, and cannot serve as
    # the label for the snapshot before it. The cleansing layer legitimately
    # leaves nulls where a measure failed its contract, and coercing those to 0
    # would teach the model that a broken row is a healthy one.
    before = len(df)
    df = df.dropna(subset=["is_stock_out_risk"])
    if before != len(df):
        print(f"dropped {before - len(df):,} rows with an unknown state")

    df["usage_to_capacity_ratio"] = (
        df["average_daily_usage_litres"] / df["capacity_litres"])
    df["headroom_above_reorder"] = (
        df["stock_on_hand_litres"] - df["reorder_point_litres"])
    # Calendar flags come from dim_date and should never be null; filling
    # explicitly rather than casting means a null is treated as "not a
    # weekend" instead of raising three steps later.
    for flag in ("is_weekend", "is_public_holiday_za"):
        df[flag] = df[flag].fillna(False).astype("int8")

    df = build_next_snapshot_target(df)
    median_horizon = float(df["horizon_days"].median())
    print(f"predicting the next snapshot: median horizon "
          f"{median_horizon:.0f} days")
    print(f"target base rate, next snapshot: {df.target_stock_out.mean():.1%}")

    train, test = time_split(df, "snapshot_ts", holdout_frac=0.25)
    cols = NUMERIC + CATEGORICAL + ["is_weekend", "is_public_holiday_za"]
    X_train, y_train = as_model_matrix(train, cols), train["target_stock_out"]
    X_test, y_test = as_model_matrix(test, cols), test["target_stock_out"]

    params = dict(max_iter=300, learning_rate=0.08, max_depth=7,
                  min_samples_leaf=40, random_state=42)

    with mlflow.start_run(run_name="hgbc_stock_out_risk"):
        log_common_tags("stock_out_risk", "location x product x snapshot",
                        "is_stock_out_risk at next snapshot")
        mlflow.log_params(params)
        mlflow.log_param("target", "is_stock_out_risk at next snapshot")
        mlflow.log_param("median_horizon_days", median_horizon)
        mlflow.log_param("leak_avoided",
                         "target measured after every feature; scoring the "
                         "current snapshot instead returns ROC-AUC 0.998, "
                         "which is the definition, not a result")
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
        log_sklearn_model(pipeline)

        summarise("Stock-out risk", metrics)
        if metrics["roc_auc"] < 0.6:
            print(
                f"\n  NOTE: no usable signal at this cadence. The median gap\n"
                f"  between snapshots of the same tank is "
                f"{median_horizon:.0f} days, and a level\n"
                "  today does not predict a level a quarter later -- the tank\n"
                "  is refilled and drawn down repeatedly in between.\n\n"
                "  Scored against the *current* snapshot the same model\n"
                "  reaches ROC-AUC 0.998, because the target is a ratio of two\n"
                "  of its own features. That version is the only learnable\n"
                "  one, which is exactly why the leak was worth finding.\n\n"
                "  The fix is denser data: feed this model from the tank\n"
                "  telemetry stream rather than from quarterly snapshots.")
        print("\n" + classification_report(
            y_test, (proba > threshold).astype(int),
            target_names=["healthy", "at risk"], digits=3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
