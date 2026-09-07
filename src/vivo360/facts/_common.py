"""Shared helpers for fact generation.

The important behaviour here is `sample_timestamps`: transaction times are not
uniform. They follow hour-of-day commute peaks, day-of-week shape, monthly
seasonality and South African public holidays, so downstream forecasting and
anomaly-detection models have real signal to learn.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config
from .. import reference as ref

_DAY_CACHE: dict[tuple, tuple[np.ndarray, np.ndarray]] = {}


def _day_distribution() -> tuple[np.ndarray, np.ndarray]:
    """Day offsets across the modelled window and their sampling weights."""
    key = (config.DATE_START, config.DATE_END)
    if key in _DAY_CACHE:
        return _DAY_CACHE[key]

    days = pd.date_range(config.DATE_START, config.DATE_END, freq="D")
    w = np.ones(len(days), dtype=float)
    w *= np.array([ref.DOW_WEIGHTS[d] for d in days.dayofweek])
    w *= np.array([ref.MONTH_WEIGHTS[m] for m in days.month])

    holidays = set(pd.to_datetime(sorted(ref.SA_PUBLIC_HOLIDAYS)))
    is_hol = np.array([d in holidays for d in days])
    w *= np.where(is_hol, 0.86, 1.0)
    # The day before a public holiday is the busiest fuel day of all.
    pre_hol = np.roll(is_hol, -1)
    w *= np.where(pre_hol, 1.34, 1.0)

    # Gentle year-on-year volume growth plus a mild demand cycle.
    t = np.arange(len(days)) / max(1, len(days) - 1)
    w *= 1.0 + 0.09 * t
    w *= 1.0 + 0.035 * np.sin(2 * np.pi * np.arange(len(days)) / 91.0)

    w /= w.sum()
    offsets = np.arange(len(days))
    _DAY_CACHE[key] = (offsets, w)
    return offsets, w


def sample_timestamps(rng, n: int, hourly: bool = True) -> pd.Series:
    """Draw `n` timestamps shaped by real trading rhythms."""
    offsets, w = _day_distribution()
    day = rng.choice(offsets, n, p=w)

    if hourly:
        hw = np.array(ref.HOUR_WEIGHTS, dtype=float)
        hw /= hw.sum()
        hour = rng.choice(24, n, p=hw)
    else:
        hour = rng.integers(0, 24, n)

    minute = rng.integers(0, 60, n)
    second = rng.integers(0, 60, n)
    base = np.datetime64(config.DATE_START, "s")
    delta = (day.astype("int64") * 86400
             + hour.astype("int64") * 3600
             + minute.astype("int64") * 60
             + second.astype("int64"))
    return pd.Series(pd.to_datetime(base + delta.astype("timedelta64[s]")))


def uniform_timestamps(rng, n: int) -> pd.Series:
    """Flat timestamps, for processes with no intraday shape (snapshots)."""
    span_days = (config.DATE_END - config.DATE_START).days
    base = np.datetime64(config.DATE_START, "s")
    delta = rng.integers(0, span_days * 86400, n)
    return pd.Series(pd.to_datetime(base + delta.astype("timedelta64[s]")))


def date_key(ts) -> np.ndarray:
    return _acc(ts).strftime("%Y%m%d").astype("int32").to_numpy()


def time_key(ts) -> np.ndarray:
    a = _acc(ts)
    return (a.hour * 60 + a.minute).astype("int16").to_numpy()


def _acc(ts):
    """Datetime accessor for either a Series or a DatetimeIndex."""
    return ts.dt if isinstance(ts, pd.Series) else ts


def seq_ids(prefix: str, offset: int, n: int, width: int = 12) -> np.ndarray:
    """Globally unique surrogate business keys for a chunk starting at `offset`."""
    return np.char.add(prefix, np.char.zfill(
        (np.arange(offset + 1, offset + n + 1)).astype(str), width))


def weighted_sites(rng, ctx, n: int) -> np.ndarray:
    """Pick sites in proportion to how busy they are."""
    return rng.choice(ctx.site_ids, n, p=ctx.site_demand)


def price_path(ts: pd.Series, base_price: float, rng, n: int) -> np.ndarray:
    """Regulated fuel prices move in monthly steps, not continuously.

    South African pump prices are adjusted on the first Wednesday of each month,
    so the synthetic price is a per-month step function plus a small zone
    differential rather than random noise on every transaction.
    """
    a = _acc(ts)
    months = np.asarray(a.year) * 12 + np.asarray(a.month)
    m0 = months.min()
    idx = months - m0
    n_months = int(idx.max()) + 1
    # A persistent random walk gives a believable price history.
    walk = np.cumsum(rng.normal(0.0, 0.42, n_months))
    walk = walk - walk[0]
    monthly_price = base_price + walk
    monthly_price = np.clip(monthly_price, base_price * 0.72, base_price * 1.34)
    zone_diff = rng.normal(0, 0.22, n)
    return np.round(monthly_price[idx] + zone_diff, 3)


def add_audit_columns(df: pd.DataFrame, source_code: str) -> pd.DataFrame:
    """Lineage columns every bronze record carries."""
    df["source_system_code"] = source_code
    df["ingested_at"] = pd.Timestamp(config.DATE_END) + pd.Timedelta(hours=3)
    return df
