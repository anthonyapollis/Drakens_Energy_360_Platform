"""Site-level daily fuel demand forecast.

Business question: how much fuel will each site sell tomorrow, so replenishment
can be planned before the tank runs low rather than after.

Grain: one row per site per day, from `agg_site_daily_fuel`.

Two decisions worth stating:

* **Lag features, not future features.** Everything the model sees is known at
  the point of prediction. It is trivially easy to build a forecast that scores
  brilliantly by including the day's own transaction count, and it is useless.
* **A seasonal-naive baseline is reported alongside.** "MAPE of 12%" means
  nothing on its own. What matters is whether it beats predicting last week's
  same weekday, which costs nothing to implement.
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import (
    mean_absolute_error,
    mean_absolute_percentage_error,
    r2_score,
)

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
    a.date_key,
    a.full_date,
    a.site_key,
    a.province,
    a.urban_class,
    a.site_type,
    a.demand_band,
    a.litres,
    a.transaction_count,
    a.gross_margin_pct,
    a.loyalty_penetration_pct,
    a.diesel_share_pct,
    d.day_of_week,
    d.month_number,
    d.is_weekend,
    d.is_public_holiday_za,
    d.school_holiday_za,
    d.season_southern
from main_gold.agg_site_daily_fuel a
join main_gold.dim_date d on a.date_key = d.date_key
where a.litres > 0
"""


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["site_key", "full_date"]).copy()
    g = df.groupby("site_key", observed=True)["litres"]

    # Everything below is known strictly before the day being predicted.
    for lag in (1, 2, 7, 14, 28):
        df[f"litres_lag_{lag}"] = g.shift(lag)
    for window in (7, 28):
        df[f"litres_roll_mean_{window}"] = (
            g.shift(1).rolling(window, min_periods=max(2, window // 4)).mean()
        )
        df[f"litres_roll_std_{window}"] = (
            g.shift(1).rolling(window, min_periods=max(2, window // 4)).std()
        )

    # Momentum: this week against the month, which is what actually separates a
    # site that is growing from one that is merely large.
    df["trend_ratio"] = df["litres_roll_mean_7"] / df["litres_roll_mean_28"]

    # The day before a public holiday is the strongest fuel day of the year,
    # so the model needs to see it coming, not just recognise it afterwards.
    df["is_day_before_holiday"] = (
        df.groupby("site_key", observed=True)["is_public_holiday_za"]
        .shift(-1).fillna(False).astype(bool)
    )

    df["day_of_week"] = df["day_of_week"].astype("int8")
    df["month_number"] = df["month_number"].astype("int8")
    return df.dropna(subset=["litres_lag_28", "litres_roll_mean_28"])


FEATURES = [
    "litres_lag_1", "litres_lag_2", "litres_lag_7", "litres_lag_14", "litres_lag_28",
    "litres_roll_mean_7", "litres_roll_mean_28",
    "litres_roll_std_7", "litres_roll_std_28",
    "trend_ratio", "day_of_week", "month_number",
    "is_weekend", "is_public_holiday_za", "is_day_before_holiday",
    "school_holiday_za",
]
CATEGORICAL = ["province", "urban_class", "site_type", "demand_band", "season_southern"]


def main() -> int:
    start_experiment("demand_forecast")
    raw = load(QUERY)
    print(f"loaded {len(raw):,} site-days across {raw.site_key.nunique():,} sites")

    df = build_features(raw)
    for col in CATEGORICAL:
        df[col] = df[col].astype("category")
    train, test = time_split(df, "full_date", holdout_frac=0.2)
    print(f"train {len(train):,} rows to {train.full_date.max().date()}, "
          f"test {len(test):,} rows from {test.full_date.min().date()}")

    cols = FEATURES + CATEGORICAL
    X_train, y_train = train[cols], train["litres"]
    X_test, y_test = test[cols], test["litres"]

    params = dict(max_iter=400, learning_rate=0.06, max_depth=8,
                  min_samples_leaf=40, l2_regularization=1.0,
                  early_stopping=True, validation_fraction=0.12,
                  random_state=42)

    with mlflow.start_run(run_name="hgbr_site_daily_litres"):
        log_common_tags("demand_forecast", "site x day", "litres")
        mlflow.log_params(params)
        mlflow.log_param("n_features", len(cols))
        mlflow.log_param("train_rows", len(train))
        mlflow.log_param("test_rows", len(test))

        model = HistGradientBoostingRegressor(
            categorical_features=CATEGORICAL, **params)
        model.fit(X_train, y_train)
        pred = model.predict(X_test)

        # The baseline any forecast must beat: same weekday, last week.
        baseline = test["litres_lag_7"]

        metrics = {
            "mae": mean_absolute_error(y_test, pred),
            "mape": mean_absolute_percentage_error(y_test, pred),
            "r2": r2_score(y_test, pred),
            "rmse": float(np.sqrt(np.mean((y_test - pred) ** 2))),
            "baseline_mae": mean_absolute_error(y_test, baseline),
            "baseline_mape": mean_absolute_percentage_error(y_test, baseline),
        }
        metrics["mae_improvement_pct"] = (
            (metrics["baseline_mae"] - metrics["mae"]) / metrics["baseline_mae"] * 100
        )
        mlflow.log_metrics(metrics)
        log_sklearn_model(model)

        summarise("Demand forecast (site x day litres)", metrics)
        if metrics["mae_improvement_pct"] <= 0:
            print("  WARNING: the model does not beat the seasonal-naive "
                  "baseline. It should not be promoted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
