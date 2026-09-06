"""Build orchestrator: generate the full synthetic lake for a scale profile."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import config, dimensions, facts
from .writer import LakeWriter

DISCLAIMER = (
    "Independent synthetic portfolio project. Contains no internal Vivo Energy, "
    "Engen, Shell or Vitol data. All sites, customers, prices, volumes, assets "
    "and coordinates are randomly generated."
)


def build(profile_name: str, output: Path, fmt: str = "parquet",
          seed: int = config.DEFAULT_SEED, only: list[str] | None = None,
          verbose: bool = True) -> dict:
    profile = config.resolve(profile_name)
    registry = facts.load_all()
    plan = config.planned_fact_rows(profile)

    missing = sorted(set(plan) - set(registry))
    if missing:
        raise RuntimeError(
            f"{len(missing)} planned fact tables have no generator: {missing}"
        )

    rng = np.random.default_rng(seed)
    writer = LakeWriter(output, fmt=fmt)

    t0 = time.perf_counter()
    if verbose:
        print(f"[1/2] dimensions  profile={profile_name}")
    ctx = dimensions.build_all(rng, profile, writer)
    t_dim = time.perf_counter() - t0
    if verbose:
        n_dim = sum(1 for k in writer.stats if not k.startswith("fact_"))
        print(f"      {n_dim} tables, "
              f"{sum(s.rows for s in writer.stats.values()):,} rows in {t_dim:,.1f}s")

    targets = sorted(plan) if only is None else [t for t in sorted(plan) if t in only]
    if verbose:
        print(f"[2/2] facts       {len(targets)} tables, "
              f"{sum(plan[t] for t in targets):,} planned rows")

    t1 = time.perf_counter()
    for i, name in enumerate(targets, start=1):
        rows = plan[name]
        make_chunk = registry[name](rng, ctx, profile)
        ts = time.perf_counter()
        stat = writer.write_fact(name, rows, make_chunk)
        if verbose:
            print(f"      {i:>3}/{len(targets)}  {name:<38} "
                  f"{stat.rows:>10,} rows  {stat.bytes/1e6:>7.1f} MB  "
                  f"{time.perf_counter()-ts:>6.1f}s")
    t_fact = time.perf_counter() - t1

    manifest_extra = {
        "profile": profile_name,
        "seed": seed,
        "disclaimer": DISCLAIMER,
        "date_start": str(config.DATE_START),
        "date_end": str(config.DATE_END),
        "dimension_build_seconds": round(t_dim, 2),
        "fact_build_seconds": round(t_fact, 2),
        "total_build_seconds": round(time.perf_counter() - t0, 2),
    }
    path = writer.write_manifest(manifest_extra)
    manifest = json.loads(path.read_text(encoding="utf-8"))

    if verbose:
        print(f"\ndone  {manifest['fact_rows']:,} fact rows across "
              f"{manifest['fact_tables']} fact tables")
        print(f"      {manifest['dimension_rows']:,} dimension rows across "
              f"{manifest['dimension_tables']} tables")
        print(f"      {manifest['total_bytes']/1e9:.2f} GB on disk in "
              f"{manifest['total_build_seconds']:,.0f}s")
        print(f"      manifest: {path}")

    if profile_name == "portfolio" and manifest["fact_rows"] < config.MIN_PORTFOLIO_FACT_ROWS:
        raise RuntimeError(
            f"portfolio build produced {manifest['fact_rows']:,} fact rows, "
            f"below the {config.MIN_PORTFOLIO_FACT_ROWS:,} floor"
        )
    return manifest


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="vivo360-build",
        description="Generate the Vivo Energy 360 synthetic data lake.",
        epilog=DISCLAIMER,
    )
    ap.add_argument("--profile", default="dev", choices=sorted(config.PROFILES))
    ap.add_argument("--output", default="data/lake", type=Path)
    ap.add_argument("--format", default="parquet", choices=["parquet", "csv"])
    ap.add_argument("--seed", type=int, default=config.DEFAULT_SEED)
    ap.add_argument("--only", nargs="*", default=None,
                    help="restrict the build to named fact tables")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    build(args.profile, args.output, args.format, args.seed,
          args.only, verbose=not args.quiet)


if __name__ == "__main__":
    main()
