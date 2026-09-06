"""Build orchestrator: generate the full synthetic lake for a scale profile."""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from . import config, dimensions, dirty, facts
from .writer import LakeWriter, logical_types


def writer_types(clean_chunk):
    """Logical types of a fact table, sampled from one clean row."""
    return logical_types(clean_chunk(0, 1))

DISCLAIMER = (
    "Independent synthetic portfolio project. Contains no internal Vivo Energy, "
    "Engen, Shell or Vitol data. All sites, customers, prices, volumes, assets "
    "and coordinates are randomly generated."
)


def build(profile_name: str, output: Path, fmt: str = "parquet",
          seed: int = config.DEFAULT_SEED, only: list[str] | None = None,
          verbose: bool = True, defects: str = "realistic") -> dict:
    profile = config.resolve(profile_name)
    defect_profile = dirty.resolve(defects)
    registry = facts.load_all()
    plan = config.planned_fact_rows(profile)

    missing = sorted(set(plan) - set(registry))
    if missing:
        raise RuntimeError(
            f"{len(missing)} planned fact tables have no generator: {missing}"
        )

    rng = np.random.default_rng(seed)
    # A separate stream so toggling the defect profile never shifts the
    # underlying clean data. The same seed produces the same business facts
    # whether or not defects are injected, which makes the cleansing layer
    # testable against a known-good baseline.
    injector = dirty.DefectInjector(
        defect_profile, np.random.default_rng(seed + 7919))
    writer = LakeWriter(output, fmt=fmt)

    t0 = time.perf_counter()
    if verbose:
        print(f"[1/2] dimensions  profile={profile_name}")
    ctx = dimensions.build_all(rng, profile, writer, injector)
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
        clean_chunk = registry[name](rng, ctx, profile)

        def make_chunk(offset, n, _fn=clean_chunk, _name=name):
            return injector.apply(_name, _fn(offset, n))

        # Capture the intended column types from a clean single-row sample.
        # Defect injection deliberately turns numbers into text, so the types
        # must be read before damage, not inferred from the landing zone.
        intended = writer_types(clean_chunk)

        ts = time.perf_counter()
        stat = writer.write_fact(name, rows, make_chunk, types=intended)
        if verbose:
            print(f"      {i:>3}/{len(targets)}  {name:<38} "
                  f"{stat.rows:>10,} rows  {stat.bytes/1e6:>7.1f} MB  "
                  f"{time.perf_counter()-ts:>6.1f}s")
    t_fact = time.perf_counter() - t1

    defect_summary = injector.summary()
    manifest_extra = {
        "profile": profile_name,
        "seed": seed,
        "disclaimer": DISCLAIMER,
        # The cleansing layer is validated against these counts: every defect
        # injected here must be either repaired or quarantined downstream.
        "data_quality": defect_summary,
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
        dq = defect_summary
        print(f"\ndefect profile '{dq['defect_profile']}': "
              f"{dq['total_defects_injected']:,} defects injected")
        for defect, count in list(dq["defects_by_type"].items())[:14]:
            print(f"      {defect:<32} {count:>12,}")

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
    ap.add_argument("--defects", default="realistic",
                    choices=sorted(dirty.PROFILES),
                    help="how damaged the landing zone should be")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    build(args.profile, args.output, args.format, args.seed,
          args.only, verbose=not args.quiet, defects=args.defects)


if __name__ == "__main__":
    main()
