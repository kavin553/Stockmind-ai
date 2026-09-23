from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.ml.features import (
    FEATURE_COLUMNS,
    StaticFeatures,
    build_feature_row,
    build_supervised,
    daily_series,
    time_split,
)
from app.ml.forecast import forecast_bundle, train

TODAY = date.today()
STATIC = StaticFeatures(current_stock=100, inventory_age=80, selling_price=250.0, discount_pct=0.0, category_code=3, store_code=1)


class _Sale:
    def __init__(self, sold_on, quantity):
        self.sold_on = sold_on
        self.quantity = quantity


def _steady_series(days: int = 300, qty: float = 3.0) -> pd.Series:
    sales = [_Sale(TODAY - timedelta(days=offset), int(qty)) for offset in range(days)]
    return daily_series(sales, TODAY, days)


def test_feature_windows_only_look_backwards():
    series = _steady_series(days=200, qty=2)
    day = series.index[-1]
    row = build_feature_row(series, day, STATIC)
    # No feature may exceed the cumulative activity before the prediction day.
    prior_total = float(series.loc[series.index < day].sum())
    assert row["sales_60d"] <= prior_total + 1e-9
    assert row["sales_30d"] <= row["sales_60d"] + 1e-9
    assert row["sales_7d"] <= row["sales_30d"] + 1e-9
    assert set(FEATURE_COLUMNS).issubset(row.keys())


def test_features_ignore_future_rows():
    series = _steady_series(days=200, qty=1)
    day = series.index[150]
    before = build_feature_row(series, day, STATIC)
    mutated = series.copy()
    mutated.loc[series.index[160:]] = 9999.0  # inject future spikes
    after = build_feature_row(mutated, day, STATIC)
    assert before == after


def test_time_split_validation_is_strictly_after_training():
    series = _steady_series(days=300, qty=2)
    frame, target, days = build_supervised(series, STATIC)
    x_train, y_train, x_val, y_val = time_split(frame, target, days)
    assert len(x_train) + len(x_val) == len(frame)
    if len(x_val):
        # The last training row must precede the first validation row in time.
        train_max = days[len(x_train) - 1]
        val_min = days[len(x_train)]
        assert val_min > train_max


def test_cold_start_uses_category_baseline_with_low_confidence():
    sales = [_Sale(TODAY - timedelta(days=10), 2), _Sale(TODAY - timedelta(days=40), 1)]
    series = daily_series(sales, TODAY, 180)
    category = pd.Series(2.0, index=pd.date_range(end=pd.Timestamp(TODAY), periods=90, freq="D"))
    result = forecast_bundle(series, STATIC, as_of=TODAY, category_daily=category)
    assert result["method"] == "category_baseline"
    assert result["confidence"] < 0.5
    assert result["predictions"][7] > 0


def test_forecasts_are_non_negative_and_monotonic_in_horizon():
    result = forecast_bundle(_steady_series(days=300, qty=3), STATIC, as_of=TODAY)
    predictions = result["predictions"]
    assert all(v >= 0 for v in predictions.values())
    assert predictions[60] >= predictions[30] >= predictions[7]


def test_metrics_come_from_the_holdout_not_the_training_set():
    trained = train(_steady_series(days=320, qty=3), STATIC)
    assert trained.method in ("xgboost", "hist_gradient_boosting")
    metrics = trained.metrics
    assert metrics["validation_rows"] > 0
    assert "mae" in metrics and "rmse" in metrics and "smape" in metrics
    assert metrics["train_rows"] + metrics["validation_rows"] > 0
    assert 0.0 <= metrics["smape"] <= 2.0


def test_model_does_not_claim_perfect_accuracy():
    trained = train(_steady_series(days=320, qty=3), STATIC)
    assert trained.confidence <= 0.95  # never fabricate a perfect score
