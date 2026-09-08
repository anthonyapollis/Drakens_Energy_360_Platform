"""Publish the MLflow results as a table the warehouse and Power BI can read.

Six models are trained, tracked and compared against baselines, and none of it
reached the semantic model -- so the Power BI project had no ML in it at all.
The work existed; it was just invisible to the one artifact anybody opens.

This reads the MLflow SQLite store and writes one row per model: the headline
metric, the baseline it has to beat, the lift over that baseline, and a verdict
derived from the two. The verdict is the point. Two of these models do not beat
their baseline, and a scorecard that quietly omitted them would be worth less
than no scorecard: a model that loses to "predict the mean" is a finding, and
publishing it is what makes the other four credible.

Usage:
    python scripts/export_ml_results.py
    python scripts/export_ml_results.py --out powerbi/data/obs_ml_performance.csv
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MLRUNS = REPO / "mlruns" / "mlflow.db"
DEFAULT_OUT = REPO / "powerbi" / "data" / "obs_ml_performance.csv"

# The headline metric differs by task: a classifier is judged on ranking, a
# forecast on error.
#
# The baseline for a classifier is NOT base_rate. base_rate is the prevalence
# of the positive class -- 0.14 for stock-outs -- and comparing an ROC-AUC to
# it is comparing two different quantities. Doing exactly that scored a 0.501
# model, which is chance, as "+0.361 over baseline" and reported five of five
# models beating their baselines. The real comparison is against 0.5, or
# against a purpose-built baseline where the experiment recorded one.
CHANCE_AUC = 0.5

# Experiments that record their own baseline, and the metric holding it. An
# age-only model is a much harder baseline than chance, and it is the honest
# one for predictive maintenance: knowing an asset is old is free.
EXPLICIT_BASELINE = {
    "predictive_maintenance": "baseline_roc_auc_age_only",
}

SCORING = {
    "classification": ("roc_auc", True),
    "regression": ("mae", False),
}

# Which experiments are regression rather than classification.
REGRESSION = {"demand_forecast"}

# A model has to clear its baseline by this much to count as useful. A
# classifier one point of AUC above chance is not a model, it is noise with a
# decimal point.
MEANINGFUL_LIFT = 0.02


def latest_runs(con: sqlite3.Connection) -> list[dict]:
    """The most recent finished run per experiment.

    Earlier runs are kept in the store deliberately -- the leakage fix on
    stock_out_risk is only legible next to the 0.998 that preceded it -- but a
    scorecard reports the current state, not the history.
    """
    rows = con.execute("""
        select e.name, r.run_uuid, r.start_time
        from runs r
        join experiments e on e.experiment_id = r.experiment_id
        where r.status = 'FINISHED'
        order by e.name, r.start_time desc
    """).fetchall()
    seen: dict[str, tuple[str, int]] = {}
    for name, run_id, started in rows:
        if name not in seen:
            seen[name] = (run_id, started)
    return [{"experiment": n, "run_id": r, "started": s}
            for n, (r, s) in seen.items()]


def metrics_for(con: sqlite3.Connection, run_id: str) -> dict[str, float]:
    return dict(con.execute(
        "select key, value from metrics where run_uuid = ?", [run_id]))


def tags_for(con: sqlite3.Connection, run_id: str) -> dict[str, str]:
    return dict(con.execute(
        "select key, value from tags where run_uuid = ?", [run_id]))


def params_for(con: sqlite3.Connection, run_id: str) -> dict[str, str]:
    return dict(con.execute(
        "select key, value from params where run_uuid = ?", [run_id]))


def verdict(lift: float | None, higher_is_better: bool) -> str:
    if lift is None:
        return "No baseline recorded"
    if not higher_is_better:
        lift = -lift
    if lift >= MEANINGFUL_LIFT:
        return "Beats baseline"
    if lift > 0:
        return "Marginal over baseline"
    return "Does not beat baseline"


def _unscored(model: str, tags: dict) -> dict:
    return {
        "model": model.replace("_", " ").title(),
        "model_key": model,
        "task": "unsupervised",
        "use_case": tags.get("use_case", ""),
        "target": tags.get("target", ""),
        "grain": tags.get("grain", ""),
        "metric_name": "",
        "metric_value": None,
        "baseline_name": "",
        "baseline_value": None,
        "lift_over_baseline": None,
        "higher_is_better": True,
        "verdict": "Not scored (unsupervised)",
        "train_rows": 0,
        "test_rows": 0,
        "n_features": 0,
        "interpretation": tags.get("interpretation", ""),
        "disclaimer": tags.get(
            "disclaimer",
            "Synthetic data. Drakens Energy is a fictional company."),
    }


def build_rows(con: sqlite3.Connection) -> list[dict]:
    out = []
    for run in latest_runs(con):
        name = run["experiment"]
        # The project was renamed. An experiment still carrying the old name
        # is a stale run against a real company's name, and does not belong in
        # a published scorecard.
        if not name.startswith("drakens_energy_360_"):
            continue
        model = name.removeprefix("drakens_energy_360_")
        metrics = metrics_for(con, run["run_id"])
        tags = tags_for(con, run["run_id"])
        params = params_for(con, run["run_id"])

        task = "regression" if model in REGRESSION else "classification"
        metric_key, higher = SCORING[task]
        score = metrics.get(metric_key)
        if score is None:
            # fraud_anomaly is unsupervised and records no scored metric.
            # Listing it with an empty verdict is more honest than dropping
            # it: a reader counting models on the page should see all six.
            out.append(_unscored(model, tags))
            continue

        if task == "regression":
            baseline_key = "baseline_mae"
            baseline = metrics.get(baseline_key)
        else:
            baseline_key = EXPLICIT_BASELINE.get(model)
            if baseline_key and baseline_key in metrics:
                baseline = metrics[baseline_key]
            else:
                baseline_key = "chance (0.5)"
                baseline = CHANCE_AUC
        lift = None if baseline is None else round(score - baseline, 6)

        out.append({
            "model": model.replace("_", " ").title(),
            "model_key": model,
            "task": task,
            "use_case": tags.get("use_case", ""),
            "target": tags.get("target", ""),
            "grain": tags.get("grain", ""),
            "metric_name": metric_key,
            "metric_value": round(score, 6),
            "baseline_name": baseline_key,
            "baseline_value": None if baseline is None else round(baseline, 6),
            "lift_over_baseline": lift,
            "higher_is_better": higher,
            "verdict": verdict(lift, higher),
            "train_rows": int(params.get("train_rows", 0) or 0),
            "test_rows": int(params.get("test_rows", 0) or 0),
            "n_features": int(params.get("n_features", 0) or 0),
            "interpretation": tags.get("interpretation", ""),
            "disclaimer": tags.get(
                "disclaimer",
                "Synthetic data. Drakens Energy is a fictional company."),
        })
    return sorted(out, key=lambda r: (r["verdict"], r["model"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mlruns", type=Path, default=MLRUNS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    if not args.mlruns.exists():
        print(f"no MLflow store at {args.mlruns}; run the experiments first")
        return 1

    con = sqlite3.connect(f"file:{args.mlruns}?mode=ro", uri=True)
    try:
        rows = build_rows(con)
    finally:
        con.close()

    if not rows:
        print("no finished runs found")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} model(s) to {args.out.relative_to(REPO)}")
    for row in rows:
        lift = ("   n/a" if row["lift_over_baseline"] is None
                else f"{row['lift_over_baseline']:+.3f}")
        score = ("      --" if row["metric_value"] is None
                 else f"{row['metric_value']:.3f}")
        print(f"  {row['model']:26} {row['metric_name'] or '-':>8}={score}"
              f"  lift {lift}  {row['verdict']}")
    beaten = sum(1 for r in rows if r["verdict"] == "Beats baseline")
    scored = sum(1 for r in rows if r["metric_value"] is not None)
    print(f"\n{beaten} of {scored} scored models beat their baseline "
          f"({len(rows) - scored} unscored)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
