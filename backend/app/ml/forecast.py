"""Demand forecasting: XGBoost with a legitimate time-ordered holdout, plus a deterministic
cold-start baseline.

Design notes
------------
* The regressor predicts **daily units**. Horizons are produced by walking the calendar forward
  and feeding predictions back into the rolling windows — so ``forecast_60d`` is a genuine
  60-step-ahead path, not ``3 × forecast_20d``.
* Model metrics (MAE / RMSE / sMAPE) are reported **from the holdout only**.
* When history is thin the model is not trusted: a category-level baseline is used and the
  confidence is marked low / ``method="category_baseline"``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.config import policy
from app.ml.features import FEATURE_COLUMNS, StaticFeatures, build_feature_row, build_supervised, time_split

try:  # pragma: no cover - environment dependent
    from xgboost import XGBRegressor

    _HAS_XGB = True
except Exception:  # pragma: no cover
    XGBRegressor = None  # type: ignore[assignment]
    _HAS_XGB = False

from sklearn.ensemble import HistGradientBoostingRegressor


@dataclass
class TrainedForecaster:
    model: object
    feature_names: list[str]
    metrics: dict
    method: str
    history: pd.Series
    static: StaticFeatures
    confidence: float
    notes: list[str] = field(default_factory=list)


def _make_regressor():
    if _HAS_XGB:
        return XGBRegressor(
            n_estimators=250,
            max_depth=4,
            learning_rate=0.06,
            subsample=0.9,
            colsample_bytree=0.9,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=2,
            objective="reg:squarederror",
        )
    return HistGradientBoostingRegressor(random_state=42, max_depth=4, learning_rate=0.08)


def _smape(actual: np.ndarray, predicted: np.ndarray) -> float:
    denom = (np.abs(actual) + np.abs(predicted)) / 2.0
    mask = denom > 0
    if not mask.any():
        return 0.0
    return float(np.mean(np.abs(actual[mask] - predicted[mask]) / denom[mask]))


def train(
    series: pd.Series,
    static: StaticFeatures,
    category_daily: pd.Series | None = None,
) -> TrainedForecaster:
    """Train on the product's own history, or fall back to a category baseline."""
    nonzero_days = int((series > 0).sum())
    notes: list[str] = []

    if nonzero_days < policy.cold_start_min_sales_days:
        method = "category_baseline" if category_daily is not None else "insufficient_history"
        baseline_daily = (
            float(category_daily.tail(policy.category_baseline_window_days).mean())
            if category_daily is not None and len(category_daily)
            else 0.0
        )
        notes.append(
            f"Only {nonzero_days} selling days of history — the model is not trained; a "
            f"category baseline of {baseline_daily:.2f} units/day is used instead."
        )
        confidence = min(0.35, 0.10 + 0.01 * nonzero_days)
        return TrainedForecaster(
            model=None,
            feature_names=FEATURE_COLUMNS,
            metrics={"baseline_daily_units": round(baseline_daily, 4), "selling_days": nonzero_days},
            method=method,
            history=series,
            static=static,
            confidence=round(confidence, 4),
            notes=notes,
        )

    frame, target, _ = build_supervised(series, static)
    if len(frame) < 10:
        notes.append("Too few supervised rows to validate a model.")
        baseline_daily = float(series.mean())
        return TrainedForecaster(
            model=None,
            feature_names=FEATURE_COLUMNS,
            metrics={"baseline_daily_units": round(baseline_daily, 4), "selling_days": nonzero_days},
            method="seasonal_naive",
            history=series,
            static=static,
            confidence=0.3,
            notes=notes,
        )

    x_train, y_train, x_val, y_val = time_split(frame, target, pd.DatetimeIndex([]))
    model = _make_regressor()
    model.fit(x_train, y_train)

    predictions = np.clip(np.asarray(model.predict(x_val), dtype=float), 0.0, None)
    mae = float(np.mean(np.abs(np.asarray(y_val) - predictions))) if len(y_val) else 0.0
    rmse = float(np.sqrt(np.mean((np.asarray(y_val) - predictions) ** 2))) if len(y_val) else 0.0
    smape = _smape(np.asarray(y_val, dtype=float), predictions) if len(y_val) else 1.0

    # Refit on all data once the holdout has been measured.
    final_model = _make_regressor()
    final_model.fit(frame, target)

    history_adequacy = min(1.0, nonzero_days / 120.0)
    accuracy = max(0.0, 1.0 - smape)
    confidence = round(max(0.05, min(0.95, 0.55 * accuracy + 0.45 * history_adequacy)), 4)

    notes.append(
        f"Time-ordered holdout of {len(x_val)} days: MAE {mae:.2f}, RMSE {rmse:.2f}, "
        f"sMAPE {smape:.1%}."
    )
    return TrainedForecaster(
        model=final_model,
        feature_names=FEATURE_COLUMNS,
        metrics={
            "mae": round(mae, 4),
            "rmse": round(rmse, 4),
            "smape": round(smape, 4),
            "train_rows": int(len(x_train)),
            "validation_rows": int(len(x_val)),
            "selling_days": nonzero_days,
        },
        method="xgboost" if _HAS_XGB else "hist_gradient_boosting",
        history=series,
        static=static,
        confidence=confidence,
        notes=notes,
    )


def _future_row(history: pd.Series, day: pd.Timestamp, static: StaticFeatures) -> dict:
    row = build_feature_row(history, day, static)
    return row


def _path_totals(
    trained: TrainedForecaster, horizons: list[int], as_of: pd.Timestamp
) -> dict[int, float]:
    """Walk the calendar once to the longest horizon, feeding predictions back into the
    rolling windows, and record the cumulative total at each requested horizon.

    One pass (rather than one pass per horizon) keeps forecasting cheap enough to warm up
    every SKU in the demo seed.
    """
    horizons = sorted(h for h in horizons if h > 0)
    if not horizons:
        return {}

    if trained.model is None:
        baseline = float(trained.metrics.get("baseline_daily_units", 0.0))
        totals: dict[int, float] = {}
        running = 0.0
        for step in range(1, horizons[-1] + 1):
            day = as_of + pd.Timedelta(days=step)
            running += baseline * (1.15 if day.dayofweek >= 5 else 1.0)
            if step in horizons:
                totals[step] = running
        return totals

    history = trained.history.copy()
    totals = {}
    running = 0.0
    for step in range(1, horizons[-1] + 1):
        day = as_of + pd.Timedelta(days=step)
        row = _future_row(history, day, trained.static)
        frame = pd.DataFrame([row], columns=trained.feature_names)
        prediction = float(np.clip(np.asarray(trained.model.predict(frame), dtype=float)[0], 0.0, None))
        running += prediction
        history.loc[day] = prediction
        if step in horizons:
            totals[step] = running
    return totals


def forecast_bundle(
    series: pd.Series,
    static: StaticFeatures,
    as_of: date,
    horizons: list[int] | None = None,
    category_daily: pd.Series | None = None,
) -> dict:
    """Produce ``{7: units, 30: units, 60: units}`` plus confidence and metrics."""
    horizons = horizons or policy.forecast_horizons
    trained = train(series, static, category_daily=category_daily)
    as_of_ts = pd.Timestamp(as_of)
    totals = _path_totals(trained, horizons, as_of_ts)
    predictions = {h: round(max(0.0, totals.get(h, 0.0)), 2) for h in sorted(horizons)}
    predictions = _enforce_monotonic(predictions)
    return {
        "predictions": predictions,
        "confidence": trained.confidence,
        "method": trained.method,
        "metrics": trained.metrics,
        "notes": trained.notes,
    }


def _enforce_monotonic(predictions: dict[int, float]) -> dict[int, float]:
    """A longer horizon cannot forecast fewer units than a shorter one for the same origin."""
    ordered = sorted(predictions)
    result: dict[int, float] = {}
    previous = 0.0
    for horizon in ordered:
        value = max(previous, predictions[horizon])
        result[horizon] = round(value, 2)
        previous = value
    return result
