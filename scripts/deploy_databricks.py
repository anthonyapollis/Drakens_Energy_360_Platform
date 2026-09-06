"""Deploy the Vivo Energy 360 platform to a Databricks workspace.

Creates the Unity Catalog structure, uploads the notebooks and (optionally)
creates and runs the medallion job. Uses OAuth via the Databricks CLI profile,
so no token is ever read, written or printed by this script.

Usage:
    python scripts/deploy_databricks.py --profile pet-business --env dev
    python scripts/deploy_databricks.py --profile pet-business --env dev --run
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import jobs, workspace
from databricks.sdk.service.sql import StatementState

REPO_ROOT = Path(__file__).resolve().parent.parent
NOTEBOOK_DIR = REPO_ROOT / "databricks" / "notebooks"

SCHEMAS = {
    "bronze": "Raw landing zone. Append-only, schema-on-read, no business logic.",
    "silver": "Cleaned, typed, deduplicated and conformed business events.",
    "silver_snapshots": "dbt Type-2 snapshots of slowly changing dimensions.",
    "gold": "Dimensional marts and aggregates serving Power BI and ML.",
    "platform": "Operational metadata: run log, data quality, freshness, controls.",
    "ml": "Feature tables, model inputs and scored outputs.",
}

CATALOG_COMMENT = (
    "Vivo Energy 360 synthetic downstream-energy platform. Independent "
    "portfolio project; contains no internal Vivo Energy, Engen, Shell or "
    "Vitol data. All sites, customers, prices and coordinates are generated."
)


def run_sql(w: WorkspaceClient, warehouse_id: str, statement: str,
            timeout: str = "50s") -> None:
    """Execute one SQL statement, raising on failure."""
    resp = w.statement_execution.execute_statement(
        warehouse_id=warehouse_id, statement=statement, wait_timeout=timeout
    )
    state = resp.status.state
    # A warehouse cold start can exceed the wait timeout; poll until settled.
    while state in (StatementState.PENDING, StatementState.RUNNING):
        time.sleep(5)
        resp = w.statement_execution.get_statement(resp.statement_id)
        state = resp.status.state
    if state != StatementState.SUCCEEDED:
        msg = resp.status.error.message if resp.status.error else "unknown error"
        raise RuntimeError(f"SQL failed ({state}): {msg}\n  statement: {statement[:160]}")
    print(f"  ok  {statement[:78]}")


def ensure_warehouse(w: WorkspaceClient) -> str:
    warehouses = list(w.warehouses.list())
    if not warehouses:
        raise RuntimeError("no SQL warehouse available in this workspace")
    wh = warehouses[0]
    print(f"warehouse: {wh.name} ({wh.id}) state={wh.state}")
    return wh.id


def create_catalog(w: WorkspaceClient, warehouse_id: str, env: str) -> str:
    catalog = f"vivo_{env}"
    print(f"\n[1/3] Unity Catalog: {catalog}")
    run_sql(w, warehouse_id,
            f"CREATE CATALOG IF NOT EXISTS {catalog} COMMENT '{CATALOG_COMMENT}'")
    for schema, comment in SCHEMAS.items():
        run_sql(w, warehouse_id,
                f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema} COMMENT '{comment}'")
    return catalog


def upload_notebooks(w: WorkspaceClient, base_path: str) -> list[str]:
    print(f"\n[2/3] Notebooks -> {base_path}")
    w.workspace.mkdirs(base_path)
    uploaded = []
    for nb in sorted(NOTEBOOK_DIR.glob("*.py")):
        target = f"{base_path}/{nb.stem}"
        w.workspace.upload(
            path=target,
            content=nb.read_bytes(),
            format=workspace.ImportFormat.SOURCE,
            language=workspace.Language.PYTHON,
            overwrite=True,
        )
        uploaded.append(target)
        print(f"  ok  {nb.name} -> {target}")
    return uploaded


def create_job(w: WorkspaceClient, base_path: str, catalog: str,
               env: str, scale: str) -> int:
    """Create (or update) the medallion job and return its id."""
    print(f"\n[3/3] Job: vivo360_medallion_{env}")
    name = f"vivo360_medallion_{env}"

    params = {"catalog": catalog, "scale": scale, "seed": "3602026"}
    tasks = []
    ordered = [
        ("generate_bronze", "00_generate_bronze_at_scale", []),
        ("build_silver", "02_silver_conformance", ["generate_bronze"]),
        ("build_gold", "03_gold_star_schema", ["build_silver"]),
        ("data_quality", "05_data_quality_checks", ["build_gold"]),
        ("optimize_tables", "06_optimize_and_vacuum", ["data_quality"]),
    ]
    for task_key, notebook, depends in ordered:
        nb_path = f"{base_path}/{notebook}"
        try:
            w.workspace.get_status(nb_path)
        except Exception:                                    # noqa: BLE001
            print(f"  skip {task_key}: {notebook} not uploaded")
            continue
        tasks.append(jobs.Task(
            task_key=task_key,
            notebook_task=jobs.NotebookTask(
                notebook_path=nb_path, base_parameters=params),
            depends_on=[jobs.TaskDependency(task_key=d) for d in depends] or None,
            timeout_seconds=7200,
        ))

    existing = next((j for j in w.jobs.list(name=name)), None)
    settings = jobs.JobSettings(
        name=name,
        tasks=tasks,
        max_concurrent_runs=1,
        tags={"project": "vivo_energy_360", "environment": env,
              "data": "synthetic"},
    )
    if existing:
        w.jobs.reset(job_id=existing.job_id, new_settings=settings)
        print(f"  ok  updated job {existing.job_id} with {len(tasks)} tasks")
        return existing.job_id

    created = w.jobs.create(name=name, tasks=tasks, max_concurrent_runs=1,
                            tags=settings.tags)
    print(f"  ok  created job {created.job_id} with {len(tasks)} tasks")
    return created.job_id


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="pet-business")
    ap.add_argument("--env", default="dev", choices=["dev", "test", "prod"])
    ap.add_argument("--scale", default="demo",
                    choices=["demo", "portfolio", "enterprise"])
    ap.add_argument("--run", action="store_true", help="trigger the job after deploy")
    ap.add_argument("--wait", action="store_true", help="block until the run finishes")
    args = ap.parse_args(argv)

    w = WorkspaceClient(profile=args.profile)
    print(f"workspace: {w.config.host}")
    print(f"user:      {w.current_user.me().user_name}")

    warehouse_id = ensure_warehouse(w)
    catalog = create_catalog(w, warehouse_id, args.env)

    user = w.current_user.me().user_name
    base_path = f"/Users/{user}/vivo_energy_360"
    upload_notebooks(w, base_path)

    job_id = create_job(w, base_path, catalog, args.env, args.scale)
    print(f"\njob url: {w.config.host}/jobs/{job_id}")

    if args.run:
        run = w.jobs.run_now(job_id=job_id)
        print(f"triggered run {run.run_id}")
        print(f"run url: {w.config.host}/jobs/{job_id}/runs/{run.run_id}")
        if args.wait:
            result = run.result()
            print(f"final state: {result.state.result_state}")
            if result.state.result_state != jobs.RunResultState.SUCCESS:
                return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
