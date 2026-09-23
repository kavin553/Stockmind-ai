# `ml/` — forecasting experiments

The runtime forecasting code lives in `backend/app/ml/` so the API can import it directly.
This directory holds the offline / evaluation entry points.

## Run

```bash
# from the repository root, with the backend dependencies installed and a seeded database
python -m ml.train_forecaster --sample 25
```

It reports **holdout** MAE / RMSE / sMAPE from a strictly time-ordered split. There is no
random train/test split anywhere in the pipeline — every validation row comes *after* every
training row, and the rolling feature windows only ever look backwards.

## Model

* `XGBRegressor` (gradient-boosted trees) predicting **daily units**.
* Horizons are produced by walking the calendar forward and feeding predictions back into the
  rolling windows, so `forecast_60d` is a genuine 60-step path.
* Cold-start SKUs (fewer than `COLD_START_MIN_SALES_DAYS` selling days) skip the model entirely
  and use a category-level baseline, reported with low confidence and
  `method = "category_baseline"`.

## Features

`sales_7d`, `sales_14d`, `sales_30d`, `sales_60d`, `average_daily_sales`, `sales_trend`,
`sales_volatility`, `days_since_last_sale`, `inventory_age`, `current_stock`, `selling_price`,
`discount_percentage`, `category`, `store`, `month`, `day_of_week`, `weekend_flag`,
`promotion_flag`, `season`.

## Honesty rules

* Metrics are always reported from the holdout, never the training set.
* Confidence is capped below 1.0 — the product never claims perfect accuracy.
* When history is insufficient the model says so rather than emitting a confident guess.
