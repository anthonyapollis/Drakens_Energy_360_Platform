"""Memory-bounded Parquet output for the synthetic lake.

Fact tables are written as Hive-style partitioned datasets of part files so a
multi-million-row table never has to exist in memory at once. The layout is
readable directly by DuckDB, Spark, Databricks Auto Loader and dbt.
"""
from __future__ import annotations

import json
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from . import config


@dataclass
class TableStat:
    name: str
    rows: int
    files: int
    bytes: int
    columns: list[str] = field(default_factory=list)
    # The *intended* type of each column, captured before defect injection
    # turns numbers into text. The dbt cleansing layer is generated from this,
    # so it knows what a column is supposed to be rather than guessing from
    # the damaged landing-zone data.
    intended_types: dict = field(default_factory=dict)



def logical_types(df: pd.DataFrame) -> dict:
    """Map each column to a logical type the cleansing layer can act on."""
    out = {}
    for col in df.columns:
        dt = df[col].dtype
        if pd.api.types.is_bool_dtype(dt):
            out[col] = "boolean"
        elif pd.api.types.is_datetime64_any_dtype(dt):
            out[col] = "timestamp"
        elif pd.api.types.is_integer_dtype(dt):
            out[col] = "integer"
        elif pd.api.types.is_float_dtype(dt):
            out[col] = "decimal"
        elif col.endswith(("_id", "_code")):
            out[col] = "code"
        else:
            out[col] = "text"
    return out


class LakeWriter:
    """Writes dimension and fact tables into a raw landing zone."""

    def __init__(self, root: Path, fmt: str = "parquet", overwrite: bool = True):
        self.root = Path(root)
        self.fmt = fmt
        if overwrite and self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.stats: dict[str, TableStat] = {}

    # ---------------------------------------------------------------- dims
    def write_dimension(self, name: str, df: pd.DataFrame,
                        types: dict | None = None) -> TableStat:
        folder = self.root / "dimensions" / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.{self.fmt}"
        if self.fmt == "csv":
            df.to_csv(path, index=False)
        else:
            df.to_parquet(path, index=False, compression="snappy")
        stat = TableStat(name, len(df), 1, path.stat().st_size,
                         list(df.columns), types or logical_types(df))
        self.stats[name] = stat
        return stat

    # --------------------------------------------------------------- facts
    def write_fact(
        self,
        name: str,
        total_rows: int,
        make_chunk: Callable[[int, int], pd.DataFrame],
        chunk_rows: int | None = None,
        types: dict | None = None,
    ) -> TableStat:
        """Materialise `total_rows` of a fact table via repeated chunk calls.

        `make_chunk(offset, n)` must return exactly `n` rows and is responsible
        for producing globally unique surrogate keys from `offset`.
        """
        chunk_rows = chunk_rows or config.CHUNK_ROWS
        folder = self.root / "facts" / name
        folder.mkdir(parents=True, exist_ok=True)

        written = 0
        files = 0
        size = 0
        columns: list[str] = []
        types: dict = dict(types or {})
        for offset, n in _chunks(total_rows, chunk_rows):
            df = make_chunk(offset, n)
            if len(df) != n:
                raise ValueError(
                    f"{name}: chunk returned {len(df)} rows, expected {n}"
                )
            if not columns:
                columns = list(df.columns)
            path = folder / f"part-{offset:012d}.{self.fmt}"
            if self.fmt == "csv":
                df.to_csv(path, index=False)
            else:
                df.to_parquet(path, index=False, compression="snappy")
            written += n
            files += 1
            size += path.stat().st_size

        stat = TableStat(name, written, files, size, columns, types)
        self.stats[name] = stat
        return stat

    # -------------------------------------------------------------- manifest
    def write_manifest(self, extra: dict | None = None) -> Path:
        dims = {k: v for k, v in self.stats.items() if k.startswith("dim_") or k.startswith("bridge_")}
        facts = {k: v for k, v in self.stats.items() if k.startswith("fact_")}
        manifest = {
            "format": self.fmt,
            "dimension_tables": len(dims),
            "fact_tables": len(facts),
            "dimension_rows": sum(s.rows for s in dims.values()),
            "fact_rows": sum(s.rows for s in facts.values()),
            "total_rows": sum(s.rows for s in self.stats.values()),
            "total_bytes": sum(s.bytes for s in self.stats.values()),
            "tables": {
                name: {
                    "rows": s.rows,
                    "files": s.files,
                    "bytes": s.bytes,
                    "columns": s.columns,
                    "intended_types": s.intended_types,
                }
                for name, s in sorted(self.stats.items())
            },
        }
        if extra:
            manifest.update(extra)
        path = self.root / "_manifest.json"
        path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return path

    @property
    def fact_rows(self) -> int:
        return sum(s.rows for s in self.stats.values() if s.name.startswith("fact_"))


def _chunks(total: int, size: int) -> Iterator[tuple[int, int]]:
    for start in range(0, total, size):
        yield start, min(size, total - start)
