"""Shared plumbing for the MLflow experiments.

All six experiments read from the gold marts rather than from raw files. That
is deliberate: a model trained on a different definition of "OTIF" or
"stock-out" from the one the dashboard uses will eventually disagree with the
business, and nobody will be able to say which is right. Reading from gold
means the model and the report share one definition by construction.
"""
from __future__ import annotations

import os
from pathlib import Path

import duckdb
import mlflow
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "data" / "vivo360.duckdb"
MLRUNS = REPO_ROOT / "mlruns"

DISCLAIMER = (
    "Independent synthetic portfolio project. Models are trained on generated "
    "data and carry no predictive claim about any real company."
)


def connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = Path(os.environ.get("VIVO_DUCKDB_PATH", db_path or DEFAULT_DB))
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Build the warehouse first:\n"
            f"  python -m vivo360.build --profile portfolio --output data/lake\n"
            f"  cd dbt && dbt build"
        )
    return duckdb.connect(str(path), read_only=True)


def load(sql: str, db_path: Path | None = None) -> pd.DataFrame:
    with connect(db_path) as con:
        return con.execute(sql).df()


def start_experiment(name: str) -> None:
    """Point MLflow at the local tracking store and select the experiment.

    On Databricks this would be `mlflow.set_tracking_uri("databricks")` and a
    workspace experiment path; the experiment code itself is unchanged.
    """
    MLRUNS.mkdir(exist_ok=True)
    mlflow.set_tracking_uri(f"file:///{MLRUNS.as_posix()}")
    mlflow.set_experiment(f"/vivo_energy_360/{name}")


def log_common_tags(use_case: str, grain: str, target: str) -> None:
    mlflow.set_tags({
        "project": "vivo_energy_360",
        "use_case": use_case,
        "grain": grain,
        "target": target,
        "data": "synthetic",
        "disclaimer": DISCLAIMER,
    })


def time_split(df: pd.DataFrame, date_col: str, holdout_frac: float = 0.2):
    """Split chronologically, never randomly.

    A random split on time-series data leaks the future into training and
    produces an accuracy figure that will not survive contact with production.
    The holdout is always the most recent period.
    """
    df = df.sort_values(date_col)
    cut = int(len(df) * (1 - holdout_frac))
    return df.iloc[:cut].copy(), df.iloc[cut:].copy()


def summarise(name: str, metrics: dict) -> None:
    print(f"\n{name}")
    print("-" * len(name))
    for k, v in metrics.items():
        print(f"  {k:<28} {v:,.4f}" if isinstance(v, float) else f"  {k:<28} {v}")
