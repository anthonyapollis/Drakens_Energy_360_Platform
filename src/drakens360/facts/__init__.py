"""Fact-table generator registry.

Each fact table registers a *builder*: a function taking (rng, ctx, profile)
and returning a `make_chunk(offset, n) -> DataFrame` closure. The writer calls
that closure repeatedly so a 5-million-row table is produced in bounded memory.
"""
from __future__ import annotations

from collections.abc import Callable

import pandas as pd

ChunkFn = Callable[[int, int], pd.DataFrame]
Builder = Callable[..., ChunkFn]

REGISTRY: dict[str, Builder] = {}


def fact(name: str):
    """Decorator registering a fact-table builder under `name`."""

    def wrap(fn: Builder) -> Builder:
        if name in REGISTRY:
            raise KeyError(f"fact {name!r} registered twice")
        REGISTRY[name] = fn
        return fn

    return wrap


def load_all() -> dict[str, Builder]:
    """Import every domain module so the registry is fully populated."""
    from . import (  # noqa: F401
        assets,
        commercial,
        digital,
        energy,
        finance,
        hsseq,
        logistics,
        products,
        retail,
        supply,
    )

    return REGISTRY
