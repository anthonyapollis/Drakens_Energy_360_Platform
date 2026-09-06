"""Predict commercial customer churn.

Business question: which B2B accounts are about to stop buying, early enough
for an account manager to intervene.

Grain: one row per customer per month, from `agg_customer_monthly`.

Churn has to be *defined* before it can be predicted, and the definition is a
business choice rather than a technical one. Here a customer has churned if
they bought nothing in the following 90 days having been active before. That
is stated in one place, in SQL, so the model and any dashboard reporting
"churn rate" cannot drift apart.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.inspection import permutation_importance
from sklearn.metrics import (average_precision_score, classification_report,
                             roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import load, log_common_tags, start_experiment, summarise, time_split  # noqa: E402

# Three consecutive months with no order is the churn definition. It is long
# enough to survive a customer's ordinary ordering rhythm and short enough
# that intervention is still possible.
CHURN_HORIZON_MONTHS = 3

QUERY = """
select
    m.year_month,
    m.calendar_year,
    m.month_number,
    m.customer_key,
    m.customer_id,
    m.sector,
    m.segment,
    m.credit_band,
    m.credit_risk_tier,
    m.order_count,
    m.cancelled_orders,
    m.volume_litres,
    m.revenue_zar,
    m.gross_margin_zar,
    m.discount_value_zar,
    m.margin_pct,
    m.avg_order_value_zar,
    m.discount_intensity_pct,
    m.volume_mom_pct,
    m.revenue_mom_pct,
    m.is_sharp_decline
from main_gold.agg_customer_monthly m
order by m.customer_key, m.year_month
"""

NUMERIC = [
    "order_count", "cancelled_orders", "volume_litres", "revenue_zar",
    "gross_margin_zar", "discount_value_zar", "margin_pct",
    "avg_order_value_zar", "discount_intensity_pct",
    "volume_mom_pct", "revenue_mom_pct",
    "months_active", "months_since_first_order",
    "volume_vs_own_average", "consecutive_declining_months",
]
CATEGORICAL = ["sector", "segment", "credit_band", "credit_risk_tier"]


def build_target(df: pd.DataFrame) -> pd.DataFrame:
    """Label a customer-month as churn if no order follows within the horizon."""
    df = df.sort_values(["customer_key", "year_month"]).copy()
    df["month_index"] = (
        df["calendar_year"].astype(int) * 12 + df["month_number"].astype(int))

    g = df.groupby("customer_key", observed=True)
    # The next month in which this customer actually ordered.
    df["next_active_month"] = g["month_index"].shift(-1)
    last_month = df["month_index"].max()

    gap = df["next_active_month"] - df["month_index"]
    # No further activity and enough time has elapsed to be sure.
    never_returns = df["next_active_month"].isna() & (
        last_month - df["month_index"] >= CHURN_HORIZON_MONTHS)
    df["churned"] = (gap > CHURN_HORIZON_MONTHS) | never_returns

    # Rows too recent to label either way are excluded rather than assumed
    # active; assuming would teach the model that recency means loyalty.
    df["is_labelable"] = (
        df["next_active_month"].notna()
        | (last_month - df["month_index"] >= CHURN_HORIZON_MONTHS))

    # Behavioural features
    df["months_active"] = g.cumcount() + 1
    first = g["month_index"].transform("min")
    df["months_since_first_order"] = df["month_index"] - first
    own_avg = g["volume_litres"].transform(
        lambda s: s.shift(1).expanding().mean())
    df["volume_vs_own_average"] = df["volume_litres"] / own_avg.replace(0, np.nan)
    declining = (df["volume_mom_pct"].fillna(0) < 0).astype(int)
    df["consecutive_declining_months"] = (
        declining.groupby(
            [df["customer_key"], (declining == 0).cumsum()]).cumsum())
    return df


def main() -> int:
    start_experiment("customer_churn")
    raw = load(QUERY)
    print(f"loaded {len(raw):,} customer-months across "
          f"{raw.customer_key.nunique():,} customers")

    df = build_target(raw)
    df = df[df["is_labelable"]].copy()
    df = df.replace([np.inf, -np.inf], np.nan)
    print(f"labelable rows: {len(df):,}   churn rate: {df.churned.mean():.1%}")

    if df["churned"].nunique() < 2:
        print("target has a single class after labelling; "
              "widen the date window before training")
        return 1

    train, test = time_split(df, "month_index", holdout_frac=0.25)
    cols = NUMERIC + CATEGORICAL
    X_train, y_train = train[cols], train["churned"].astype(int)
    X_test, y_test = test[cols], test["churned"].astype(int)

    params = dict(max_iter=300, learning_rate=0.06, max_depth=6,
                  min_samples_leaf=40, l2_regularization=1.0, random_state=42)

    with mlflow.start_run(run_name="hgbc_customer_churn"):
        log_common_tags("customer_churn", "customer x month", "churned")
        mlflow.log_params(params)
        mlflow.log_param("churn_horizon_months", CHURN_HORIZON_MONTHS)
        mlflow.log_param("train_rows", len(train))
        mlflow.log_param("test_rows", len(test))

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
        # An account manager can only call so many customers. What matters is
        # how many real churners are in the list they are handed.
        for k in (5, 10, 20):
            n = max(1, int(len(proba) * k / 100))
            top = np.argsort(-proba)[:n]
            metrics[f"precision_at_top_{k}pct"] = float(y_test.iloc[top].mean())
            metrics[f"revenue_at_risk_top_{k}pct_zar"] = float(
                test.iloc[top]["revenue_zar"].sum())
        mlflow.log_metrics(metrics)
        mlflow.sklearn.log_model(pipeline, name="model")

        summarise("Customer churn", metrics)
        print("\n" + classification_report(
            y_test, (proba > 0.5).astype(int),
            target_names=["retained", "churned"], digits=3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
