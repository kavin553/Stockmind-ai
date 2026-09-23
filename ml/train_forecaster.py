"""Standalone demand-forecasting evaluation.

Trains the forecaster for a sample of SKUs and reports **holdout** metrics (MAE / RMSE /
sMAPE) from a strictly time-ordered split, so the numbers are never training-set numbers.

    python -m ml.train_forecaster --sample 25
"""
from __future__ import annotations

import argparse
import statistics
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.models import Inventory  # noqa: E402
from app.ml.features import StaticFeatures, daily_series  # noqa: E402
from app.ml.forecast import train  # noqa: E402
from app.services.demand_forecast_service import category_daily_series, sales_series  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the demand forecaster on holdout data.")
    parser.add_argument("--sample", type=int, default=25, help="number of inventory rows to sample")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        rows = list(session.scalars(select(Inventory).limit(args.sample)))
        if not rows:
            print("No inventory found. Run `python -m app.seed.seed` first.")
            return

        smapes, methods = [], []
        for inventory in rows:
            product, store = inventory.product, inventory.store
            series = sales_series(session, product.id, store.id)
            category_series = category_daily_series(session, product.category_id, store.id)
            static = StaticFeatures(
                current_stock=inventory.quantity,
                inventory_age=(date.today() - inventory.first_received_at).days,
                selling_price=float(product.list_price),
                discount_pct=float(inventory.discount_pct),
            )
            trained = train(series, static, category_daily=category_series)
            methods.append(trained.method)
            if "smape" in trained.metrics:
                smapes.append(trained.metrics["smape"])

        print(f"SKUs evaluated: {len(rows)}")
        print(f"Methods: { {m: methods.count(m) for m in set(methods)} }")
        if smapes:
            print(f"Holdout sMAPE — mean {statistics.fmean(smapes):.2%}, "
                  f"median {statistics.median(smapes):.2%}, n={len(smapes)}")
            print("These are holdout metrics from time-ordered validation, not training fit.")
        else:
            print("No SKU had enough history to train a model; category baselines were used.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
