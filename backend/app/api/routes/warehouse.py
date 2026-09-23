from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_session
from app.models import User
from app.services import warehouse_service

router = APIRouter(prefix="/warehouse", tags=["warehouse"])


@router.get("")
def layout(
    store: str | None = Query(None, description="store code, e.g. STR-BLR-01"),
    db: Session = Depends(db_session),
    _: User = Depends(current_user),
) -> dict:
    """Rack/shelf layout with risk derived from real inventory rows.

    Locations without inventory are returned with ``unit_count = 0`` so the client can show
    "Insufficient inventory data" instead of inventing a risk colour.
    """
    try:
        return warehouse_service.warehouse_layout(db, store)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.get("/location/{location_code}")
def location(
    location_code: str,
    store: str = Query(..., description="store code"),
    db: Session = Depends(db_session),
    _: User = Depends(current_user),
) -> dict:
    try:
        return warehouse_service.location_detail(db, store, location_code)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None
