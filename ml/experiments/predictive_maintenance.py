"""Predict whether a maintenance work order will be an unplanned breakdown.

Business question: which assets should be pulled into planned maintenance
before they fail, given that a breakdown costs materially more than a planned
intervention and takes the forecourt out of service.

Grain: one row per work order, from `fct_maintenance_work_orders`.

The features are deliberately restricted to what is knowable *before* the
work order is diagnosed: asset age, criticality, type and site context. Cost
and labour hours are outcomes, not predictors -- including them would produce
an excellent-looking model that cannot be used, because those values do not
exist at the moment the decision has to be made.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    classification_report,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    load,
    log_common_tags,
    start_experiment,
    summarise,
    time_split,
)

QUERY = """
select
    w.work_order_id,
    w.raised_ts,
    w.asset_id,
    w.asset_type,
    w.criticality,
    w.asset_age_years,
    w.asset_age_band,
    w.priority,
    w.province,
    w.urban_class,
    w.demand_band,
    w.is_breakdown
from main_gold.fct_maintenance_work_orders w
where w.asset_age_years is not null
"""

NUMERIC = ["asset_age_years", "prior_breakdowns", "prior_work_orders",
           "breakdown_rate_to_date"]
CATEGORICAL = ["asset_type", "criticality", "priority", "province",
               "urban_class", "demand_band", "asset_age_band"]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add the asset's own history, computed strictly from earlier rows.

    An asset that has already broken down twice is a different proposition
    from one that never has, and this is the strongest signal available. The
    expanding counts are shifted by one so a row never sees its own outcome.
    """
    df = df.sort_values(["asset_id", "raised_ts"]).copy()
    g = df.groupby("asset_id", observed=True)
    df["prior_work_orders"] = g.cumcount()
    df["prior_breakdowns"] = (
        g["is_breakdown"].apply(lambda s: s.shift(1).fillna(False).cumsum())
        .reset_index(level=0, drop=True)
    )
    df["breakdown_rate_to_date"] = np.where(
        df["prior_work_orders"] > 0,
        df["prior_breakdowns"] / df["prior_work_orders"].replace(0, np.nan),
        0.0,
    )
    return df.fillna({"breakdown_rate_to_date": 0.0})


def main() -> int:
    start_experiment("predictive_maintenance")
    raw = load(QUERY)
    print(f"loaded {len(raw):,} work orders across {raw.asset_id.nunique():,} assets")
    print(f"breakdown rate overall: {raw.is_breakdown.mean():.1%}")

    df = build_features(raw)
    train, test = time_split(df, "raised_ts", holdout_frac=0.25)

    cols = NUMERIC + CATEGORICAL
    X_train, y_train = train[cols], train["is_breakdown"].astype(int)
    X_test, y_test = test[cols], test["is_breakdown"].astype(int)

    params = dict(max_iter=350, learning_rate=0.07, max_depth=6,
                  min_samples_leaf=30, l2_regularization=1.0,
                  random_state=42)

    with mlflow.start_run(run_name="hgbc_breakdown_probability"):
        log_common_tags("predictive_maintenance", "work order", "is_breakdown")
        mlflow.log_params(params)
        mlflow.log_param("train_rows", len(train))
        mlflow.log_param("test_rows", len(test))
        mlflow.log_param("base_rate", float(y_train.mean()))

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
            # With an imbalanced target, average precision says more about
            # usable performance than AUC does.
            "average_precision": average_precision_score(y_test, proba),
            # Calibration matters here: the output feeds a cost trade-off, so
            # a probability of 0.7 has to mean roughly 70%.
            "brier_score": brier_score_loss(y_test, proba),
            "base_rate": float(y_test.mean()),
        }

        # What the maintenance planner actually gets: the top-N riskiest
        # assets they have capacity to visit this week.
        for k in (5, 10, 20):
            n = max(1, int(len(proba) * k / 100))
            top_idx = np.argsort(-proba)[:n]
            metrics[f"precision_at_top_{k}pct"] = float(y_test.iloc[top_idx].mean())
            metrics[f"lift_at_top_{k}pct"] = float(
                y_test.iloc[top_idx].mean() / max(y_test.mean(), 1e-9))

        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(pipeline, name="model")

        summarise("Predictive maintenance (breakdown probability)", metrics)
        print("\n" + classification_report(
            y_test, (proba > 0.5).astype(int),
            target_names=["planned", "breakdown"], digits=3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
