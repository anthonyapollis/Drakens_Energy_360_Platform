"""Twelve-month-ahead revenue forecast, for every product that sells.

Business question: what will each product line bill over the next year, so
procurement, pricing and the capital plan can be built against a number rather
than last year's.

Grain: one row per product per month, across **both** channels -- retail
forecourt (`fct_retail_fuel_sales`) and commercial B2B
(`fct_commercial_orders`). Revenue is the only measure both express, which is
why the target is rand and not litres: lubricants are sold by the drum and
diesel by the litre, and a forecast that covered only one of them would miss
the largest line in the business.

Three decisions that shape what this can honestly claim:

* **Direct multi-horizon, not recursive.** A model that predicts tomorrow and
  feeds its own answer back in as yesterday compounds its error 365 times. This
  trains one model over (origin, horizon) pairs, so a 12-month-ahead
  prediction is made directly from what was known at the origin -- and the
  horizon is a feature, which lets the model learn that month 12 is harder
  than month 1.
* **Monthly grain.** A daily 365-day-ahead forecast on under three years of
  history is a random number generator with a confidence interval. The month
  is the unit a procurement plan is actually built in.
* **The history is short and the forecast says so.** 32 months exist. Holding
  out the last 12 for a backtest leaves 20 to learn from, and a seasonal-naive
  baseline needs 12 of those before it can produce anything. Every number this
  writes carries that limitation, and the per-product table reports which
  products the model beats the naive baseline on -- and which it does not.

Usage:
    python ml/experiments/product_revenue_forecast_12m.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import mlflow
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_absolute_percentage_error

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import (
    load,
    log_common_tags,
    log_sklearn_model,
    start_experiment,
    summarise,
)

REPO = Path(__file__).resolve().parent.parent.parent
OUT = REPO / "powerbi" / "data"

HORIZONS = list(range(1, 13))
BACKTEST_MONTHS = 12
MEANINGFUL_IMPROVEMENT_PCT = 5.0

QUERY = """
with retail as (
    select
        f.product_key,
        date_trunc('month', d.full_date)  as month_start,
        sum(f.gross_sales_zar)            as revenue_zar,
        sum(f.gross_margin_zar)           as margin_zar,
        sum(f.litres)                     as litres,
        'Retail'                          as channel
    from main_gold.fct_retail_fuel_sales f
    join main_gold.dim_date d on d.date_key = f.date_key
    group by 1, 2
),
commercial as (
    select
        o.product_key,
        date_trunc('month', d.full_date)  as month_start,
        sum(o.revenue_zar)                as revenue_zar,
        sum(o.gross_margin_zar)           as margin_zar,
        cast(null as double)              as litres,
        'Commercial'                      as channel
    from main_gold.fct_commercial_orders o
    join main_gold.dim_date d on d.date_key = o.date_key
    group by 1, 2
),
combined as (
    select * from retail
    union all
    select * from commercial
)
select
    c.product_key,
    p.product_name,
    p.reporting_line,
    p.category,
    p.price_regime,
    c.month_start,
    sum(c.revenue_zar) as revenue_zar,
    sum(c.margin_zar)  as margin_zar,
    sum(c.litres)      as litres,
    string_agg(distinct c.channel, ' + ') as channels
from combined c
join main_gold.dim_product p on p.product_key = c.product_key
group by all
order by c.product_key, c.month_start
"""


def monthly_panel(raw: pd.DataFrame) -> pd.DataFrame:
    """A dense product x month grid.

    A month with no sales is a zero, not a missing row. Left as missing, a lag
    silently reaches back further than it claims to and the model learns from
    a gap it cannot see.
    """
    raw["month_start"] = pd.to_datetime(raw["month_start"])
    months = pd.date_range(raw.month_start.min(), raw.month_start.max(),
                           freq="MS")
    keys = raw[["product_key", "product_name", "reporting_line", "category",
                "price_regime"]].drop_duplicates("product_key")
    grid = keys.merge(pd.DataFrame({"month_start": months}), how="cross")
    panel = grid.merge(
        raw[["product_key", "month_start", "revenue_zar", "margin_zar",
             "litres"]],
        on=["product_key", "month_start"], how="left")
    panel[["revenue_zar", "margin_zar"]] = (
        panel[["revenue_zar", "margin_zar"]].fillna(0.0))
    return panel.sort_values(["product_key", "month_start"])


def make_supervised(panel: pd.DataFrame) -> pd.DataFrame:
    """(origin, horizon) -> target revenue, using only origin-time features."""
    frames = []
    g = panel.groupby("product_key", observed=True)

    base = panel.copy()
    base["rev_last_1"] = g["revenue_zar"].shift(0)
    for lag in (1, 2, 3, 6, 11, 12):
        base[f"rev_lag_{lag}"] = g["revenue_zar"].shift(lag)
    base["rev_mean_3"] = g["revenue_zar"].transform(
        lambda s: s.rolling(3, min_periods=1).mean())
    base["rev_mean_6"] = g["revenue_zar"].transform(
        lambda s: s.rolling(6, min_periods=1).mean())
    base["rev_mean_12"] = g["revenue_zar"].transform(
        lambda s: s.rolling(12, min_periods=3).mean())
    base["rev_std_6"] = g["revenue_zar"].transform(
        lambda s: s.rolling(6, min_periods=2).std())
    # Momentum and seasonality, both computed strictly at the origin.
    base["trend_ratio"] = base["rev_mean_3"] / base["rev_mean_12"]
    base["yoy_ratio"] = base["rev_last_1"] / base["rev_lag_12"]
    base["origin_month"] = base["month_start"].dt.month

    for h in HORIZONS:
        f = base.copy()
        f["horizon"] = h
        f["target_month"] = f["month_start"] + pd.DateOffset(months=h)
        f["target_month_number"] = f["target_month"].dt.month
        f["target_quarter"] = f["target_month"].dt.quarter
        frames.append(f)

    sup = pd.concat(frames, ignore_index=True)

    # The actual for the month being predicted, and the seasonal-naive
    # baseline: the same month one year earlier, known at the origin.
    actual = panel[["product_key", "month_start", "revenue_zar"]].rename(
        columns={"month_start": "target_month", "revenue_zar": "actual"})
    sup = sup.merge(actual, on=["product_key", "target_month"], how="left")

    naive = panel[["product_key", "month_start", "revenue_zar"]].rename(
        columns={"month_start": "naive_month", "revenue_zar": "naive"})
    sup["naive_month"] = sup["target_month"] - pd.DateOffset(months=12)
    sup = sup.merge(naive, on=["product_key", "naive_month"], how="left")
    return sup


FEATURES = [
    "horizon", "origin_month", "target_month_number", "target_quarter",
    "rev_last_1", "rev_lag_1", "rev_lag_2", "rev_lag_3", "rev_lag_6",
    "rev_lag_11", "rev_lag_12",
    "rev_mean_3", "rev_mean_6", "rev_mean_12", "rev_std_6",
    "trend_ratio", "yoy_ratio",
]
CATEGORICAL = ["reporting_line", "category", "price_regime"]


def per_product(test: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, part in test.groupby("product_name", observed=True):
        part = part.dropna(subset=["actual", "pred"])
        if part.empty:
            continue
        mae = mean_absolute_error(part["actual"], part["pred"])
        with_naive = part.dropna(subset=["naive"])
        if len(with_naive):
            naive_mae = mean_absolute_error(with_naive["actual"],
                                            with_naive["naive"])
            improvement = ((naive_mae - mae) / naive_mae * 100
                           if naive_mae else 0.0)
            verdict = ("Beats seasonal-naive"
                       if improvement >= MEANINGFUL_IMPROVEMENT_PCT
                       else "Marginal over seasonal-naive" if improvement > 0
                       else "Does not beat seasonal-naive")
        else:
            naive_mae, improvement = float("nan"), float("nan")
            verdict = "No prior year to compare"
        rows.append({
            "product_name": name,
            "reporting_line": part["reporting_line"].iloc[0],
            "months_tested": len(part),
            "mean_monthly_revenue_zar": round(float(part["actual"].mean()), 2),
            "mae_zar": round(float(mae), 2),
            "mape": round(float(mean_absolute_percentage_error(
                part["actual"].clip(lower=1), part["pred"].clip(lower=0))), 4),
            "naive_mae_zar": (None if pd.isna(naive_mae)
                              else round(float(naive_mae), 2)),
            "improvement_pct": (None if pd.isna(improvement)
                                else round(float(improvement), 2)),
            "verdict": verdict,
            "disclaimer": "Synthetic data. Drakens Energy is a fictional "
                          "company.",
        })
    return pd.DataFrame(rows).sort_values("mean_monthly_revenue_zar",
                                          ascending=False)


def main() -> int:
    start_experiment("product_revenue_forecast_12m")
    raw = load(QUERY)
    panel = monthly_panel(raw)
    n_products = panel.product_key.nunique()
    print(f"{len(panel):,} product-months, {n_products} products, "
          f"{panel.month_start.min():%Y-%m} to {panel.month_start.max():%Y-%m}")

    sup = make_supervised(panel)
    last_actual = panel.month_start.max()
    cutoff = last_actual - pd.DateOffset(months=BACKTEST_MONTHS)

    # Backtest: targets in the final 12 months, from origins at or before the
    # cutoff, so nothing the model sees postdates the origin.
    trainable = sup.dropna(subset=["actual", "rev_lag_12"])
    train = trainable[trainable["target_month"] <= cutoff]
    test = trainable[(trainable["target_month"] > cutoff)
                     & (trainable["month_start"] <= cutoff)]
    print(f"train {len(train):,} (origin,horizon) pairs, "
          f"backtest {len(test):,} over the last {BACKTEST_MONTHS} months")

    if train.empty or test.empty:
        print("not enough history for a 12-month backtest")
        return 1

    for col in CATEGORICAL:
        for frame in (train, test, sup):
            frame[col] = frame[col].astype("category")

    params = dict(max_iter=400, learning_rate=0.05, max_depth=6,
                  min_samples_leaf=15, l2_regularization=1.0,
                  early_stopping=False, random_state=42)
    cols = FEATURES + CATEGORICAL

    with mlflow.start_run(run_name="hgbr_product_revenue_12m"):
        log_common_tags("product_revenue_forecast_12m",
                        "product x month x horizon", "revenue_zar")
        mlflow.log_params(params)
        mlflow.log_param("horizons", f"1-{max(HORIZONS)}")
        mlflow.log_param("n_features", len(cols))
        mlflow.log_param("train_rows", len(train))
        mlflow.log_param("test_rows", len(test))
        mlflow.log_param("products", int(n_products))
        mlflow.log_param("history_months", int(panel.month_start.nunique()))

        model = HistGradientBoostingRegressor(
            categorical_features=CATEGORICAL, **params)
        model.fit(train[cols], train["actual"])

        test = test.copy()
        test["pred"] = model.predict(test[cols]).clip(min=0)

        naive_rows = test.dropna(subset=["naive"])
        metrics = {
            "mae": mean_absolute_error(test["actual"], test["pred"]),
            "mape": mean_absolute_percentage_error(
                test["actual"].clip(lower=1), test["pred"]),
            "rmse": float(np.sqrt(np.mean((test["actual"] - test["pred"])
                                          ** 2))),
            "baseline_mae": mean_absolute_error(naive_rows["actual"],
                                                naive_rows["naive"]),
        }
        metrics["mae_improvement_pct"] = (
            (metrics["baseline_mae"] - metrics["mae"])
            / metrics["baseline_mae"] * 100)
        mlflow.log_metrics(metrics)

        # Error by horizon, which is the number anyone planning against this
        # actually needs: a forecast good at one month and useless at twelve
        # should not be quoted as one accuracy figure.
        by_h = (test.assign(err=(test["actual"] - test["pred"]).abs())
                .groupby("horizon")["err"].mean())
        for h, err in by_h.items():
            mlflow.log_metric(f"mae_horizon_{int(h):02d}", float(err))

        log_sklearn_model(model)
        scores = per_product(test)

        # Forward forecast: origin is the last actual month, horizons 1-12.
        forward = sup[(sup["month_start"] == last_actual)
                      & (sup["horizon"].isin(HORIZONS))].copy()
        forward["pred"] = model.predict(forward[cols]).clip(min=0)

        OUT.mkdir(parents=True, exist_ok=True)
        scores.to_csv(OUT / "obs_ml_product_forecast_12m.csv", index=False)

        backtest_out = test[[
            "product_name", "reporting_line", "target_month", "horizon",
            "actual", "pred", "naive"]].rename(columns={
                "target_month": "month_start", "pred": "forecast_zar",
                "actual": "actual_zar", "naive": "naive_zar"})
        backtest_out["is_forecast"] = False

        forward_out = forward[[
            "product_name", "reporting_line", "target_month", "horizon",
            "pred", "naive"]].rename(columns={
                "target_month": "month_start", "pred": "forecast_zar",
                "naive": "naive_zar"})
        forward_out["actual_zar"] = np.nan
        forward_out["is_forecast"] = True

        series = pd.concat([backtest_out, forward_out], ignore_index=True)
        series["abs_error_zar"] = (
            series["actual_zar"] - series["forecast_zar"]).abs()
        series["disclaimer"] = ("Synthetic data. Drakens Energy is a "
                                "fictional company.")
        series.to_csv(OUT / "fct_product_revenue_forecast_12m.csv",
                      index=False)

        summarise("12-month product revenue forecast", metrics)
        print("\n  mean absolute error by horizon (R):")
        for h, err in by_h.items():
            print(f"    month {int(h):>2}  {err:>16,.0f}")
        print(f"\n  per product, backtested on the last {BACKTEST_MONTHS} "
              f"months:")
        for _, r in scores.iterrows():
            naive = ("       --" if r["naive_mae_zar"] is None
                     else f"{r['naive_mae_zar']:>14,.0f}")
            imp = ("    --" if r["improvement_pct"] is None
                   else f"{r['improvement_pct']:>+6.1f}%")
            print(f"    {r['product_name'][:26]:26} mae={r['mae_zar']:>14,.0f}"
                  f"  naive={naive}  {imp}  {r['verdict']}")
        beat = int((scores.verdict == "Beats seasonal-naive").sum())
        print(f"\n  {beat} of {len(scores)} products beat seasonal-naive")
        print(f"  forward forecast written for {forward.product_key.nunique()} "
              f"products, {forward['target_month'].min():%Y-%m} to "
              f"{forward['target_month'].max():%Y-%m}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
