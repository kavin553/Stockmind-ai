"""Feature engineering for demand forecasting.

Everything here is pure: it takes a time-ordered daily sales series and produces lag/rolling
features. Windows only ever look *backwards*, which is what keeps the time-ordered validation
honest (no leakage from the future).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

SEASON_BY_MONTH = {
    1: "winter", 2: "winter", 3: "spring", 4: "spring", 5: "summer", 6: "summer",
    7: "monsoon", 8: "monsoon", 9: "autumn", 10: "autumn", 11: "festive", 12: "festive",
}
SEASON_CODES = {name: i for i, name in enumerate(sorted(set(SEASON_BY_MONTH.values())))}

FEATURE_COLUMNS = [
    "sales_7d",
    "sales_14d",
    "sales_30d",
    "sales_60d",
    "average_daily_sales",
    "sales_trend",
    "sales_volatility",
    "days_since_last_sale",
    "inventory_age",
    "current_stock",
    "selling_price",
    "discount_percentage",
    "category",
    "store",
    "month",
    "day_of_week",
    "weekend_flag",
    "promotion_flag",
    "season",
]


@dataclass(frozen=True)
class StaticFeatures:
    """Slow-moving attributes attached to every feature row."""

    current_stock: int = 0
    inventory_age: int = 0
    selling_price: float = 0.0
    discount_pct: float = 0.0
    category_code: int = 0
    store_code: int = 0
    promotion_flag: int = 0


def daily_series(sales, end_date: date, days: int) -> pd.Series:
    """Dense daily unit series ending at ``end_date`` (inclusive), zero-filled.

    ``sales`` is any iterable of objects with ``sold_on`` and ``quantity``.
    """
    index = pd.date_range(end=pd.Timestamp(end_date), periods=days, freq="D")
    series = pd.Series(0.0, index=index)
    for sale in sales:
        ts = pd.Timestamp(sale.sold_on)
        if ts in series.index:
            series.loc[ts] += float(sale.quantity)
    return series


def _days_since_last_sale(series: pd.Series) -> int:
    nonzero = np.flatnonzero(series.to_numpy())
    if len(nonzero) == 0:
        return len(series)
    return int(len(series) - 1 - nonzero[-1])


def build_feature_row(
    history: pd.Series,
    day: pd.Timestamp,
    static: StaticFeatures,
) -> dict:
    """Build the feature vector for ``day`` using only days strictly before ``day``."""
    prior = history.loc[history.index < day]
    if len(prior) == 0:
        prior = pd.Series([0.0])
    values = prior.to_numpy(dtype=float)

    def window(n: int) -> float:
        return float(values[-n:].sum()) if len(values) else 0.0

    last7 = values[-7:] if len(values) >= 7 else values
    avg_daily = float(np.mean(values)) if len(values) else 0.0
    recent = float(np.mean(last7)) if len(last7) else 0.0
    trend = recent - avg_daily
    volatility = float(np.std(last7) / recent) if recent > 0 and len(last7) > 1 else 0.0

    return {
        "sales_7d": window(7),
        "sales_14d": window(14),
        "sales_30d": window(30),
        "sales_60d": window(60),
        "average_daily_sales": avg_daily,
        "sales_trend": trend,
        "sales_volatility": volatility,
        "days_since_last_sale": _days_since_last_sale(prior),
        "inventory_age": static.inventory_age,
        "current_stock": static.current_stock,
        "selling_price": static.selling_price,
        "discount_percentage": static.discount_pct,
        "category": static.category_code,
        "store": static.store_code,
        "month": int(day.month),
        "day_of_week": int(day.dayofweek),
        "weekend_flag": int(day.dayofweek >= 5),
        "promotion_flag": static.promotion_flag,
        "season": SEASON_CODES[SEASON_BY_MONTH[int(day.month)]],
    }


def build_supervised(series: pd.Series, static: StaticFeatures) -> tuple[pd.DataFrame, pd.Series, pd.DatetimeIndex]:
    """Supervised frame: rows are days, target is that day's units, features look back."""
    rows, targets, days = [], [], []
    for day in series.index[60:]:  # need 60 days of history before the first sample
        rows.append(build_feature_row(series, day, static))
        targets.append(float(series.loc[day]))
        days.append(day)
    if not rows:
        return pd.DataFrame(columns=FEATURE_COLUMNS), pd.Series(dtype=float), pd.DatetimeIndex([])
    return pd.DataFrame(rows, columns=FEATURE_COLUMNS), pd.Series(targets, dtype=float), pd.DatetimeIndex(days)


def time_split(
    frame: pd.DataFrame,
    target: pd.Series,
    days: pd.DatetimeIndex,
    validation_fraction: float = 0.2,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    """Time-ordered split — the validation block is strictly *after* the training block."""
    if len(frame) == 0:
        return frame, target, frame, target
    cut = max(1, int(len(frame) * (1 - validation_fraction)))
    cut = min(cut, len(frame) - 1) if len(frame) > 1 else 1
    return frame.iloc[:cut], target.iloc[:cut], frame.iloc[cut:], target.iloc[cut:]
