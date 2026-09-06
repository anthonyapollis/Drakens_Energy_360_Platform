"""Detect breaking schema changes against a committed contract.

A removed column, a retyped column or a renamed table breaks every downstream
consumer -- dbt models, Power BI, the ML feature sets -- and it usually does
so silently, surfacing weeks later as a blank visual nobody can explain.

This compares the current model against `contracts/schema.json` and classifies
each difference:

  BREAKING     column or table removed, or a type narrowed. Fails the build.
  COMPATIBLE   column or table added, or a type widened. Passes with a note.

Run with --update to regenerate the contract once a change is agreed. That is
deliberately a separate, explicit action: a contract that updates itself is
not a contract.

Usage:
    python scripts/check_schema_contract.py
    python scripts/check_schema_contract.py --update
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import numpy as np                                          # noqa: E402
from vivo360 import config, dimensions, dirty, facts        # noqa: E402
from vivo360.writer import LakeWriter, logical_types        # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT = REPO / "contracts" / "schema.json"

# A type change is only safe if it cannot lose information.
WIDENING = {
    ("integer", "decimal"),
    ("integer", "text"),
    ("decimal", "text"),
    ("code", "text"),
    ("boolean", "text"),
}


def current_schema() -> dict:
    """Build the model at the smallest scale and read its shape."""
    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "lake"
    writer = LakeWriter(tmp)
    rng = np.random.default_rng(config.DEFAULT_SEED)
    injector = dirty.DefectInjector(dirty.CLEAN, np.random.default_rng(1))
    ctx = dimensions.build_all(rng, config.DEV, writer, injector)

    schema: dict[str, dict] = {}
    for name, stat in writer.stats.items():
        schema[name] = dict(stat.intended_types)

    # Fact tables are described from a single generated row rather than a full
    # build, which keeps this check to a few seconds.
    registry = facts.load_all()
    for name, builder in sorted(registry.items()):
        chunk = builder(rng, ctx, config.DEV)(0, 1)
        schema[name] = logical_types(chunk)
    return schema


def compare(current: dict, contract: dict) -> tuple[list[str], list[str]]:
    breaking: list[str] = []
    compatible: list[str] = []

    for table in sorted(set(contract) - set(current)):
        breaking.append(f"TABLE REMOVED: {table}")
    for table in sorted(set(current) - set(contract)):
        compatible.append(f"table added: {table}")

    for table in sorted(set(current) & set(contract)):
        cur_cols, con_cols = current[table], contract[table]

        for col in sorted(set(con_cols) - set(cur_cols)):
            breaking.append(f"COLUMN REMOVED: {table}.{col} "
                            f"(was {con_cols[col]})")
        for col in sorted(set(cur_cols) - set(con_cols)):
            compatible.append(f"column added: {table}.{col} "
                              f"({cur_cols[col]})")

        for col in sorted(set(cur_cols) & set(con_cols)):
            old, new = con_cols[col], cur_cols[col]
            if old == new:
                continue
            if (old, new) in WIDENING:
                compatible.append(
                    f"type widened: {table}.{col} {old} -> {new}")
            else:
                breaking.append(
                    f"TYPE CHANGED: {table}.{col} {old} -> {new}")
    return breaking, compatible


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    ap.add_argument("--update", action="store_true",
                    help="rewrite the contract from the current model")
    args = ap.parse_args(argv)

    print("deriving the current schema...")
    current = current_schema()
    print(f"  {len(current)} tables, "
          f"{sum(len(c) for c in current.values())} columns")

    if args.update or not args.contract.exists():
        args.contract.parent.mkdir(parents=True, exist_ok=True)
        args.contract.write_text(
            json.dumps(current, indent=2, sort_keys=True), encoding="utf-8")
        action = "updated" if args.update else "created"
        print(f"contract {action}: {args.contract}")
        return 0

    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    breaking, compatible = compare(current, contract)

    if compatible:
        print(f"\n{len(compatible)} compatible change(s):")
        for line in compatible[:40]:
            print(f"  {line}")
        if len(compatible) > 40:
            print(f"  ... and {len(compatible) - 40} more")

    if breaking:
        print(f"\n{len(breaking)} BREAKING change(s):")
        for line in breaking:
            print(f"  {line}")
        print("\nThese will break downstream consumers. Either revert them, or "
              "agree the change and run with --update to move the contract.")
        return 1

    print("\nno breaking changes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
