"""Inject realistic source-system defects into the generated data.

Real landing zones are not clean. A portfolio project built on perfect data
demonstrates nothing about data engineering, because the hard part of the job
is not the join -- it is deciding what to do with the row where `litres` says
`"1 234,5"`, the site code has a trailing space, and the same transaction
arrived twice because the POS replayed its batch.

This module deliberately damages the generated data in ways that mirror the
specific systems being modelled:

  Forecourt / shop POS      CSV-ish exports: numbers as text, locale decimal
                            commas, sentinel strings, thousands separators
  ERP extracts              trailing whitespace and inconsistent casing on
                            codes, replayed batches producing duplicates
  Telemetry                 sensor dropouts (nulls), stuck sentinel readings
                            (-999), clock skew producing epoch or future dates
  Manual entry              unit confusion (kilolitres typed into a litres
                            field), transposed digits, mojibake from a
                            mis-declared encoding
  Any integration           referential drift: a code present in the fact but
                            not yet in the dimension

Every defect is counted as it is applied, and the counts are written to the
manifest. That turns cleansing from an assertion into a measurement: the
pipeline is only correct if it accounts for every defect that was injected.

Defects are applied *after* a clean row is generated, so the clean value is
always the recoverable truth.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Sentinel values seen in real extracts where a NULL was meant
# --------------------------------------------------------------------------
STRING_SENTINELS = ["", " ", "NULL", "null", "N/A", "n/a", "#N/A", "-", "?",
                    "UNKNOWN", "NONE", "0"]
NUMERIC_SENTINELS = [-999, -9999, 0, 999999999]

# Text that a UTF-8 payload decoded as Latin-1 turns into. These are the
# actual byte-level results, not invented strings, which is why the
# "ambiguous unicode" warnings below are suppressed rather than corrected:
# correcting them would destroy the defect this table exists to reproduce.
MOJIBAKE = {
    "Gqeberha": "GqeberhaÂ",
    "Mbombela": "MbombelaÂ ",
    "eMalahleni": "eMalahleniÃ‚",  # noqa: RUF001
    "Cote d'Ivoire": "CÃ´te d'Ivoire",  # noqa: RUF001
    "Reunion": "RÃ©union",
}


@dataclass
class DefectProfile:
    """How damaged the landing zone is. Rates are per-row probabilities."""

    name: str
    # structural
    duplicate_rate: float = 0.0
    null_required_rate: float = 0.0
    orphan_fk_rate: float = 0.0
    # textual
    whitespace_rate: float = 0.0
    case_inconsistency_rate: float = 0.0
    sentinel_string_rate: float = 0.0
    mojibake_rate: float = 0.0
    truncated_id_rate: float = 0.0
    # numeric
    numeric_as_text_rate: float = 0.0
    locale_decimal_rate: float = 0.0
    thousands_separator_rate: float = 0.0
    unit_error_rate: float = 0.0
    negative_measure_rate: float = 0.0
    numeric_sentinel_rate: float = 0.0
    # temporal
    epoch_date_rate: float = 0.0
    future_date_rate: float = 0.0
    # semantic
    derived_mismatch_rate: float = 0.0
    currency_unflagged_rate: float = 0.0

    # Tables whose numeric columns arrive as text (CSV-style extracts).
    text_typed_tables: frozenset = field(default_factory=frozenset)


CLEAN = DefectProfile(name="clean")

# The default. Rates are low per-row but produce tens of thousands of defects
# across a 37-million-row build, which is realistic: bad data is rare per row
# and unavoidable in aggregate.
REALISTIC = DefectProfile(
    name="realistic",
    duplicate_rate=0.0025,
    null_required_rate=0.0015,
    orphan_fk_rate=0.0008,
    whitespace_rate=0.006,
    case_inconsistency_rate=0.004,
    sentinel_string_rate=0.002,
    mojibake_rate=0.0012,
    truncated_id_rate=0.0004,
    numeric_as_text_rate=1.0,          # applies only to text_typed_tables
    locale_decimal_rate=0.03,
    thousands_separator_rate=0.02,
    unit_error_rate=0.0006,
    negative_measure_rate=0.0005,
    numeric_sentinel_rate=0.0012,
    epoch_date_rate=0.0004,
    future_date_rate=0.0003,
    derived_mismatch_rate=0.0009,
    currency_unflagged_rate=0.0006,
    text_typed_tables=frozenset({
        "fact_retail_fuel_sales",
        "fact_shop_sales",
        "fact_tank_dips",
        "fact_pump_meter_readings",
    }),
)

# A deliberately hostile profile for testing that the cleansing layer holds up.
SEVERE = DefectProfile(
    name="severe",
    duplicate_rate=0.02, null_required_rate=0.012, orphan_fk_rate=0.008,
    whitespace_rate=0.04, case_inconsistency_rate=0.03,
    sentinel_string_rate=0.015, mojibake_rate=0.008, truncated_id_rate=0.004,
    numeric_as_text_rate=1.0, locale_decimal_rate=0.12,
    thousands_separator_rate=0.08, unit_error_rate=0.005,
    negative_measure_rate=0.004, numeric_sentinel_rate=0.009,
    epoch_date_rate=0.003, future_date_rate=0.002,
    derived_mismatch_rate=0.006, currency_unflagged_rate=0.004,
    text_typed_tables=frozenset({
        "fact_retail_fuel_sales", "fact_shop_sales", "fact_tank_dips",
        "fact_pump_meter_readings", "fact_commercial_orders",
        "fact_deliveries", "fact_general_ledger",
    }),
)

PROFILES = {p.name: p for p in (CLEAN, REALISTIC, SEVERE)}


# --------------------------------------------------------------------------
# Column classification
# --------------------------------------------------------------------------
# Columns that must never be null for the row to be usable. Nulling these is
# what forces a quarantine decision rather than a repair.
REQUIRED_SUFFIXES = ("_id",)

# Foreign keys that can drift out of sync with their dimension.
FK_COLUMNS = {"site_id", "product_id", "customer_id", "supplier_id",
              "terminal_id", "vehicle_id", "asset_id", "driver_id",
              "contract_id", "route_id", "depot_id"}

# Measures where a kilolitre/litre or gram/kilogram mix-up is plausible.
UNIT_ERROR_COLUMNS = {"litres", "volume_litres", "quantity_litres",
                      "delivered_litres", "stock_on_hand_litres",
                      "quantity_kg", "energy_kwh", "uplift_litres",
                      "bunker_litres"}

# Free-text columns that can carry an encoding fault.
TEXT_COLUMNS = {"site_name", "customer_name", "city", "province",
                "supplier_name", "employee_name", "product_name",
                "driver_name", "terminal_name"}

# Money columns that could arrive in the wrong currency without a flag.
MONEY_SUFFIXES = ("_zar", "_usd")


def _is_text(dtype) -> bool:
    """True for text columns under both the object and the `str` dtype.

    pandas 3 gives string columns a dedicated `str` dtype rather than
    `object`, so a bare `dtype == object` check silently matches nothing.
    """
    return (pd.api.types.is_string_dtype(dtype)
            or pd.api.types.is_object_dtype(dtype))


def _is_measure(col: str, dtype) -> bool:
    return (pd.api.types.is_numeric_dtype(dtype)
            and not pd.api.types.is_bool_dtype(dtype)
            and not col.endswith("_key")
            and col not in ("date_key", "time_key"))


def _numeric_source_columns(df: pd.DataFrame) -> list[str]:
    """Numeric columns that a CSV-style extract would deliver as text."""
    return [c for c in df.columns
            if _is_measure(c, df[c].dtype) and not c.endswith("_key")]


# --------------------------------------------------------------------------
# Injection
# --------------------------------------------------------------------------
class DefectInjector:
    """Applies a DefectProfile to generated chunks and counts what it did."""

    def __init__(self, profile: DefectProfile, rng: np.random.Generator):
        self.profile = profile
        self.rng = rng
        self.counts: dict[str, Counter] = {}

    def _bump(self, table: str, defect: str, n: int) -> None:
        if n:
            self.counts.setdefault(table, Counter())[defect] += int(n)

    def _mask(self, n: int, rate: float) -> np.ndarray:
        if rate <= 0:
            return np.zeros(n, dtype=bool)
        return self.rng.random(n) < rate

    def apply(self, table: str, df: pd.DataFrame) -> pd.DataFrame:
        """Return a damaged copy of `df`, recording every defect applied."""
        p = self.profile
        if p.name == "clean" or df.empty:
            return df

        df = df.copy()
        n = len(df)

        df = self._duplicates(table, df, n)
        df = self._text_defects(table, df, n)
        df = self._temporal_defects(table, df, n)
        df = self._semantic_defects(table, df, n)
        df = self._numeric_defects(table, df, n)
        df = self._null_required(table, df, n)
        df = self._orphan_fks(table, df, n)
        # Text typing is applied last: once a column is a string, no further
        # numeric operation would work on it.
        df = self._numeric_as_text(table, df, n)
        return df

    # ---------------------------------------------------------- structural
    def _duplicates(self, table, df, n):
        """A replayed source batch: some rows appear twice, verbatim.

        Row count is held constant by overwriting other rows, so the writer's
        chunk contract still holds. The duplicate is byte-identical including
        the business key, which is exactly what a POS replay produces.
        """
        m = self._mask(n, self.profile.duplicate_rate)
        k = int(m.sum())
        if k == 0 or n < 2:
            return df
        src = self.rng.integers(0, n, k)
        dst = np.flatnonzero(m)
        # Reindexing rather than assigning into .iloc keeps every column's
        # dtype intact; a positional block assignment forces pandas to
        # reconcile mixed dtypes and fails on narrow integer columns.
        take = np.arange(n)
        take[dst] = src
        df = df.iloc[take].reset_index(drop=True)
        self._bump(table, "duplicate_rows", k)
        return df

    def _null_required(self, table, df, n):
        """Sensor dropout or a mandatory field the source left empty."""
        for col in df.columns:
            if not col.endswith(REQUIRED_SUFFIXES):
                continue
            m = self._mask(n, self.profile.null_required_rate)
            k = int(m.sum())
            if k:
                df.loc[m, col] = None
                self._bump(table, "null_required_field", k)
        return df

    def _orphan_fks(self, table, df, n):
        """Referential drift: a code the dimension has not received yet."""
        for col in df.columns:
            if col not in FK_COLUMNS:
                continue
            m = self._mask(n, self.profile.orphan_fk_rate)
            k = int(m.sum())
            if k:
                prefix = str(df[col].dropna().iloc[0])[:1] if df[col].notna().any() else "X"
                df.loc[m, col] = [f"{prefix}999{i:05d}" for i in range(k)]
                self._bump(table, "orphan_foreign_key", k)
        return df

    # -------------------------------------------------------------- textual
    def _text_defects(self, table, df, n):
        p = self.profile
        for col in df.columns:
            if not _is_text(df[col].dtype):
                continue
            values = df[col]
            if not values.notna().any():
                continue
            # Text defects introduce values the original dtype may reject
            # (padding, sentinels); object is the permissive landing-zone type.
            df[col] = df[col].astype(object)

            # Trailing/leading whitespace on codes: survives most ETL and
            # silently breaks joins.
            m = self._mask(n, p.whitespace_rate)
            k = int(m.sum())
            if k:
                pad = self.rng.choice([" {} ", "{}  ", "  {}", "\t{}"], k)
                df.loc[m, col] = [
                    f.format(v) if isinstance(v, str) else v
                    for f, v in zip(pad, values[m], strict=False)
                ]
                self._bump(table, "whitespace_padding", k)

            # Inconsistent casing on codes: "s000123" vs "S000123".
            if col.endswith(("_id", "_code")):
                m = self._mask(n, p.case_inconsistency_rate)
                k = int(m.sum())
                if k:
                    df.loc[m, col] = [
                        v.lower() if isinstance(v, str) else v
                        for v in df.loc[m, col]
                    ]
                    self._bump(table, "case_inconsistency", k)

                # Truncated key from a fixed-width export.
                m = self._mask(n, p.truncated_id_rate)
                k = int(m.sum())
                if k:
                    df.loc[m, col] = [
                        v[:-2] if isinstance(v, str) and len(v) > 3 else v
                        for v in df.loc[m, col]
                    ]
                    self._bump(table, "truncated_identifier", k)

            # Sentinel strings standing in for NULL.
            m = self._mask(n, p.sentinel_string_rate)
            k = int(m.sum())
            if k:
                df.loc[m, col] = self.rng.choice(STRING_SENTINELS, k)
                self._bump(table, "sentinel_string", k)

            # Encoding fault from a mis-declared charset.
            if col in TEXT_COLUMNS:
                m = self._mask(n, p.mojibake_rate)
                k = int(m.sum())
                if k:
                    df.loc[m, col] = [
                        _mojibake(v) for v in df.loc[m, col]
                    ]
                    self._bump(table, "encoding_mojibake", k)
        return df

    # ------------------------------------------------------------- temporal
    def _temporal_defects(self, table, df, n):
        p = self.profile
        for col in df.columns:
            if not pd.api.types.is_datetime64_any_dtype(df[col]):
                continue

            # A device with a dead RTC reports the epoch.
            m = self._mask(n, p.epoch_date_rate)
            k = int(m.sum())
            if k:
                df.loc[m, col] = pd.Timestamp("1970-01-01")
                self._bump(table, "epoch_timestamp", k)

            # Clock skew the other way.
            m = self._mask(n, p.future_date_rate)
            k = int(m.sum())
            if k:
                df.loc[m, col] = pd.Timestamp("2099-12-31")
                self._bump(table, "future_timestamp", k)
        return df

    # ------------------------------------------------------------- semantic
    def _semantic_defects(self, table, df, n):
        p = self.profile
        cols = set(df.columns)

        # A derived total that does not agree with its own components. This is
        # the defect that most often reaches a board pack unnoticed, because
        # every individual value looks plausible.
        for total, a, b in [
            ("gross_sales_zar", "litres", "unit_price_zar"),
            ("gross_margin_zar", "gross_sales_zar", "cogs_zar"),
            ("revenue_zar", "volume_litres", "net_price_zar"),
        ]:
            if total in cols and a in cols and b in cols:
                m = self._mask(n, p.derived_mismatch_rate)
                k = int(m.sum())
                if k:
                    factor = self.rng.uniform(1.05, 1.4, k)
                    df.loc[m, total] = (
                        pd.to_numeric(df.loc[m, total], errors="coerce") * factor
                    ).round(2)
                    self._bump(table, "derived_value_mismatch", k)

        # An amount recorded in USD in a column declared as ZAR.
        for col in df.columns:
            if not col.endswith(MONEY_SUFFIXES) or not _is_measure(col, df[col].dtype):
                continue
            m = self._mask(n, p.currency_unflagged_rate)
            k = int(m.sum())
            if k:
                df.loc[m, col] = (
                    pd.to_numeric(df.loc[m, col], errors="coerce") / 18.2
                ).round(2)
                self._bump(table, "unflagged_currency", k)
        return df

    # -------------------------------------------------------------- numeric
    def _numeric_defects(self, table, df, n):
        p = self.profile
        for col in df.columns:
            if not _is_measure(col, df[col].dtype):
                continue

            # Sentinels and unit errors do not fit a narrow integer column, so
            # widen first. A real landing zone is loosely typed anyway; the
            # point of the cleansing layer is to impose the type, not inherit
            # one from the generator.
            if pd.api.types.is_integer_dtype(df[col].dtype):
                df[col] = df[col].astype("float64")

            # Kilolitres typed into a litres field.
            if col in UNIT_ERROR_COLUMNS:
                m = self._mask(n, p.unit_error_rate)
                k = int(m.sum())
                if k:
                    df.loc[m, col] = pd.to_numeric(
                        df.loc[m, col], errors="coerce") * 1000
                    self._bump(table, "unit_of_measure_error", k)

            # A sign error or a credit posted without a credit flag.
            m = self._mask(n, p.negative_measure_rate)
            k = int(m.sum())
            if k:
                df.loc[m, col] = -pd.to_numeric(
                    df.loc[m, col], errors="coerce").abs()
                self._bump(table, "negative_measure", k)

            # A stuck sensor or an ERP default.
            m = self._mask(n, p.numeric_sentinel_rate)
            k = int(m.sum())
            if k:
                df.loc[m, col] = self.rng.choice(NUMERIC_SENTINELS, k)
                self._bump(table, "numeric_sentinel", k)
        return df

    def _numeric_as_text(self, table, df, n):
        """CSV-style extracts deliver every column as text.

        Applied only to the feeds modelled as flat-file exports. Once the
        column is text it also picks up locale decimal commas and thousands
        separators, which is what actually breaks a naive CAST.
        """
        p = self.profile
        if table not in p.text_typed_tables:
            return df

        for col in _numeric_source_columns(df):
            series = pd.to_numeric(df[col], errors="coerce")
            text = series.map(lambda v: "" if pd.isna(v) else f"{v:.3f}")

            m = self._mask(n, p.locale_decimal_rate)
            k = int(m.sum())
            if k:
                text[m] = text[m].str.replace(".", ",", regex=False)
                self._bump(table, "locale_decimal_comma", k)

            m2 = self._mask(n, p.thousands_separator_rate) & ~m
            k2 = int(m2.sum())
            if k2:
                text[m2] = text[m2].map(_add_thousands_separator)
                self._bump(table, "thousands_separator", k2)

            df[col] = text
            self._bump(table, "numeric_delivered_as_text", n)
        return df

    def apply_dimension(self, table: str, df: pd.DataFrame) -> pd.DataFrame:
        """Damage master data, but never its primary key.

        Reference data is dirty in a different way from transactional feeds:
        it is hand-maintained, so it collects whitespace, inconsistent casing
        and encoding faults, but it rarely arrives duplicated or with numbers
        as text. The primary key is left intact deliberately -- a dimension
        with an unusable key is a broken extract, not a data-quality exercise,
        and it would make referential-integrity measurement meaningless.
        """
        p = self.profile
        if p.name == "clean" or df.empty:
            return df

        pk = f"{table.replace('dim_', '').replace('bridge_', '')}_id"
        df = df.copy()
        n = len(df)

        for col in df.columns:
            if col == pk or not _is_text(df[col].dtype):
                continue
            if not df[col].notna().any():
                continue
            df[col] = df[col].astype(object)

            m = self._mask(n, p.whitespace_rate)
            k = int(m.sum())
            if k:
                df.loc[m, col] = [
                    f" {v} " if isinstance(v, str) else v for v in df.loc[m, col]
                ]
                self._bump(table, "whitespace_padding", k)

            if col.endswith(("_id", "_code")):
                m = self._mask(n, p.case_inconsistency_rate)
                k = int(m.sum())
                if k:
                    df.loc[m, col] = [
                        v.lower() if isinstance(v, str) else v
                        for v in df.loc[m, col]
                    ]
                    self._bump(table, "case_inconsistency", k)

            if col in TEXT_COLUMNS:
                m = self._mask(n, p.mojibake_rate * 4)
                k = int(m.sum())
                if k:
                    df.loc[m, col] = [_mojibake(v) for v in df.loc[m, col]]
                    self._bump(table, "encoding_mojibake", k)

                m = self._mask(n, p.sentinel_string_rate)
                k = int(m.sum())
                if k:
                    df.loc[m, col] = self.rng.choice(STRING_SENTINELS, k)
                    self._bump(table, "sentinel_string", k)
        return df

    # --------------------------------------------------------------- report
    def summary(self) -> dict:
        total = sum(sum(c.values()) for c in self.counts.values())
        by_defect: Counter = Counter()
        for c in self.counts.values():
            by_defect.update(c)
        return {
            "defect_profile": self.profile.name,
            "total_defects_injected": total,
            "defects_by_type": dict(by_defect.most_common()),
            "defects_by_table": {
                t: dict(c.most_common()) for t, c in sorted(self.counts.items())
            },
        }


def _mojibake(value):
    if not isinstance(value, str):
        return value
    for good, bad in MOJIBAKE.items():
        if good in value:
            return value.replace(good, bad)
    # Generic case: re-encode as if UTF-8 bytes were read as Latin-1.
    try:
        return value.encode("utf-8").decode("latin-1")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _add_thousands_separator(text: str) -> str:
    if not text or "," in text:
        return text
    parts = text.split(".")
    whole = parts[0]
    neg = whole.startswith("-")
    whole = whole.lstrip("-")
    if len(whole) <= 3:
        return text
    grouped = f"{int(whole):,}" if whole.isdigit() else whole
    out = ("-" if neg else "") + grouped
    return out + ("." + parts[1] if len(parts) > 1 else "")


def resolve(name: str) -> DefectProfile:
    if name not in PROFILES:
        raise KeyError(f"unknown defect profile {name!r}; "
                       f"choose from {sorted(PROFILES)}")
    return PROFILES[name]
