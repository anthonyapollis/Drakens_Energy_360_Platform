"""Daily demand forecast per product, scored per product.

Business question: how much of *each grade* will the network sell tomorrow.
That is a different question from how much a site will sell, and it is the one
that drives procurement: diesel and 95 unleaded are bought separately, priced
separately, and a network-level litres number cannot be ordered against.

Grain: one row per product per day, from `fct_retail_fuel_sales`.

Three decisions worth stating:

* **One model, scored per product.** A separate model per grade would fit six
  small series; pooling them lets each grade borrow the calendar structure the
  others share, while `product_name` as a categorical keeps their levels apart.
  The evaluation is still per product, because "the model is good" is not a
  claim anyone can act on -- procurement needs to know which grade it can
  trust.
* **Lag features only.** Everything the model sees is known before the day it
  predicts. Including the day's own transaction count produces a beautiful
  score and a useless model.
* **A seasonal-naive baseline per product.** Same grade, same weekday, last
  week. A grade whose model does not beat that should be forecast by that,
  and the table says so per grade rather than hiding it in an average.
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

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "powerbi" / "data"

QUERY = """
select
    f.date_key,
    d.full_date,
    f.product_key,
    f.product_name,
    f.fuel_grade,
    f.reporting_line,
    f.is_regulated_price,
    sum(f.litres)                as litres,
    sum(f.gross_sales_zar)       as revenue_zar,
    sum(f.gross_margin_zar)      as margin_zar,
    count(*)                     as transaction_count,
    avg(f.unit_price_zar)        as avg_unit_price_zar,
    avg(f.margin_cents_per_litre) as margin_cents_per_litre,
    d.day_of_week,
    d.month_number,
    d.is_weekend,
    d.is_public_holiday_za,
    d.school_holiday_za,
    d.season_southern
from main_gold.fct_retail_fuel_sales f
join main_gold.dim_date d on d.date_key = f.date_key
where f.litres > 0
group by all
"""


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(["product_key", "full_date"]).copy()
    g = df.groupby("product_key", observed=True)["litres"]

    for lag in (1, 2, 7, 14, 28):
        df[f"litres_lag_{lag}"] = g.shift(lag)
    for window in (7, 28):
        df[f"litres_roll_mean_{window}"] = (
            g.shift(1).rolling(window, min_periods=max(2, window // 4)).mean()
        )
        df[f"litres_roll_std_{window}"] = (
            g.shift(1).rolling(window, min_periods=max(2, window // 4)).std()
        )
    df["trend_ratio"] = df["litres_roll_mean_7"] / df["litres_roll_mean_28"]

    # Price is the one driver a fuel forecast cannot ignore, and it is known
    # before the day: South African pump prices are gazetted monthly.
    p = df.groupby("product_key", observed=True)["avg_unit_price_zar"]
    df["price_lag_1"] = p.shift(1)
    df["price_change_28d"] = df["price_lag_1"] / p.shift(28) - 1

    df["is_day_before_holiday"] = (
        df.groupby("product_key", observed=True)["is_public_holiday_za"]
        .shift(-1).fillna(False).astype(bool)
    )
    df["day_of_week"] = df["day_of_week"].astype("int8")
    df["month_number"] = df["month_number"].astype("int8")
    return df.dropna(subset=["litres_lag_28", "litres_roll_mean_28",
                             "price_lag_1"])


FEATURES = [
    "litres_lag_1", "litres_lag_2", "litres_lag_7", "litres_lag_14",
    "litres_lag_28", "litres_roll_mean_7", "litres_roll_mean_28",
    "litres_roll_std_7", "litres_roll_std_28", "trend_ratio",
    "price_lag_1", "price_change_28d",
    "day_of_week", "month_number", "is_weekend", "is_public_holiday_za",
    "is_day_before_holiday", "school_holiday_za",
]
CATEGORICAL = ["product_name", "reporting_line", "season_southern"]

MEANINGFUL_IMPROVEMENT_PCT = 5.0


def per_product_scores(test: pd.DataFrame) -> pd.DataFrame:
    """Score every product separately, and say which to trust.

    An overall MAE hides the case that matters: a pooled model can look strong
    because two high-volume grades dominate the error while a third is worse
    than guessing last week. Procurement buys the third one too.
    """
    rows = []
    for name, part in test.groupby("product_name", observed=True):
        actual, pred, base = part["litres"], part["pred"], part["litres_lag_7"]
        mae = mean_absolute_error(actual, pred)
        base_mae = mean_absolute_error(actual, base)
        improvement = (base_mae - mae) / base_mae * 100 if base_mae else 0.0
        if improvement >= MEANINGFUL_IMPROVEMENT_PCT:
            verdict = "Beats seasonal-naive"
        elif improvement > 0:
            verdict = "Marginal over seasonal-naive"
        else:
            verdict = "Does not beat seasonal-naive"
        rows.append({
            "product_name": name,
            "reporting_line": part["reporting_line"].iloc[0],
            "fuel_grade": part["fuel_grade"].iloc[0],
            "is_regulated_price": bool(part["is_regulated_price"].iloc[0]),
            "test_days": len(part),
            "mean_daily_litres": round(float(actual.mean()), 1),
            "mae": round(float(mae), 2),
            "mape": round(float(
                mean_absolute_percentage_error(actual, pred)), 4),
            "baseline_mae": round(float(base_mae), 2),
            "mae_improvement_pct": round(float(improvement), 2),
            "r2": round(float(r2_score(actual, pred)), 4),
            "verdict": verdict,
            "disclaimer": "Synthetic data. Drakens Energy is a fictional "
                          "company.",
        })
    return pd.DataFrame(rows).sort_values("mean_daily_litres",
                                          ascending=False)


def main() -> int:
    start_experiment("product_demand_forecast")
    raw = load(QUERY)
    print(f"loaded {len(raw):,} product-days across "
          f"{raw.product_name.nunique()} products")

    df = build_features(raw)
    for col in CATEGORICAL:
        df[col] = df[col].astype("category")
    train, test = time_split(df, "full_date", holdout_frac=0.2)
    print(f"train {len(train):,} rows to {train.full_date.max().date()}, "
          f"test {len(test):,} rows from {test.full_date.min().date()}")

    cols = FEATURES + CATEGORICAL
    params = dict(max_iter=300, learning_rate=0.06, max_depth=6,
                  min_samples_leaf=20, l2_regularization=1.0,
                  early_stopping=True, validation_fraction=0.15,
                  random_state=42)

    with mlflow.start_run(run_name="hgbr_product_daily_litres"):
        log_common_tags("product_demand_forecast", "product x day", "litres")
        mlflow.log_params(params)
        mlflow.log_param("n_features", len(cols))
        mlflow.log_param("train_rows", len(train))
        mlflow.log_param("test_rows", len(test))
        mlflow.log_param("products", int(df.product_name.nunique()))

        model = HistGradientBoostingRegressor(
            categorical_features=CATEGORICAL, **params)
        model.fit(train[cols], train["litres"])

        test = test.copy()
        test["pred"] = model.predict(test[cols])
        baseline = test["litres_lag_7"]

        metrics = {
            "mae": mean_absolute_error(test["litres"], test["pred"]),
            "mape": mean_absolute_percentage_error(test["litres"],
                                                   test["pred"]),
            "r2": r2_score(test["litres"], test["pred"]),
            "rmse": float(np.sqrt(np.mean((test["litres"] - test["pred"])
                                          ** 2))),
            "baseline_mae": mean_absolute_error(test["litres"], baseline),
            "baseline_mape": mean_absolute_percentage_error(test["litres"],
                                                            baseline),
        }
        metrics["mae_improvement_pct"] = (
            (metrics["baseline_mae"] - metrics["mae"])
            / metrics["baseline_mae"] * 100)
        mlflow.log_metrics(metrics)
        log_sklearn_model(model)

        scores = per_product_scores(test)
        for _, r in scores.iterrows():
            # Logged per product as well as exported, so the tracking store
            # carries the same per-grade verdict the report shows.
            key = r["product_name"].lower().replace(" ", "_")[:40]
            mlflow.log_metric(f"mae__{key}", r["mae"])
            mlflow.log_metric(f"improvement_pct__{key}",
                              r["mae_improvement_pct"])

        OUT.mkdir(parents=True, exist_ok=True)
        scores.to_csv(OUT / "obs_ml_product_performance.csv", index=False)

        series = test[["full_date", "product_name", "reporting_line",
                       "fuel_grade", "litres", "pred", "litres_lag_7",
                       "margin_cents_per_litre", "avg_unit_price_zar"]].copy()
        series = series.rename(columns={"litres": "actual_litres",
                                        "pred": "forecast_litres",
                                        "litres_lag_7": "naive_litres"})
        series["abs_error_litres"] = (
            series["actual_litres"] - series["forecast_litres"]).abs()
        series.to_csv(OUT / "fct_product_demand_forecast.csv", index=False)

        summarise("Product demand forecast (product x day litres)", metrics)
        print("\n  per product:")
        for _, r in scores.iterrows():
            print(f"    {r['product_name']:26} mae={r['mae']:>9,.0f}  "
                  f"vs naive {r['baseline_mae']:>9,.0f}  "
                  f"{r['mae_improvement_pct']:>+6.1f}%  {r['verdict']}")
        beat = int((scores.verdict == "Beats seasonal-naive").sum())
        print(f"\n  {beat} of {len(scores)} products beat the seasonal-naive "
              f"baseline")
        if metrics["mae_improvement_pct"] <= 0:
            print("  WARNING: pooled model does not beat the naive baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
