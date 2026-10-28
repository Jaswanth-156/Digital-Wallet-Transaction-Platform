from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.models.suspicious_transaction import SuspiciousTransaction
from app.routers.auth import get_current_user


router = APIRouter(
    prefix="/suspicious-transactions",
    tags=["Suspicious Transactions"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_admin(current_user: User):
    role_name = getattr(current_user.role, "name", "") or ""

    if role_name.strip().upper() not in ("ADMIN", "SUPER ADMIN", "SUPER_ADMIN"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action",
        )


@router.get("/")
def get_suspicious_transactions(
    risk_level: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    query = db.query(SuspiciousTransaction)

    if risk_level:
        query = query.filter(
            SuspiciousTransaction.risk_level == risk_level.upper()
        )

    if review_status:
        query = query.filter(
            SuspiciousTransaction.status == review_status.upper()
        )

    total = query.count()

    records = (
        query.order_by(SuspiciousTransaction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [
            {
                "id": item.id,
                "transaction_id": item.transaction_id,
                "reason": item.reason,
                "risk_level": item.risk_level,
                "status": item.status,
            }
            for item in records
        ],
    }


@router.get("/{suspicious_transaction_id}")
def get_suspicious_transaction(
    suspicious_transaction_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    item = (
        db.query(SuspiciousTransaction)
        .filter(SuspiciousTransaction.id == suspicious_transaction_id)
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suspicious transaction not found",
        )

    return {
        "id": item.id,
        "transaction_id": item.transaction_id,
        "reason": item.reason,
        "risk_level": item.risk_level,
        "status": item.status,
    }


@router.patch("/{suspicious_transaction_id}/review")
def review_suspicious_transaction(
    suspicious_transaction_id: int,
    review_status: str,
    review_notes: str | None = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_admin(current_user)

    allowed_statuses = {"UNDER_REVIEW", "APPROVED", "REJECTED"}
    new_status = review_status.strip().upper()

    if new_status not in allowed_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid review status. Use UNDER_REVIEW, APPROVED, or REJECTED.",
        )

    if review_notes is not None and len(review_notes) > 1000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Review notes cannot exceed 1000 characters",
        )

    item = (
        db.query(SuspiciousTransaction)
        .filter(SuspiciousTransaction.id == suspicious_transaction_id)
        .first()
    )

    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Suspicious transaction not found",
        )

    try:
        item.status = new_status

        # Save reviewer information when these fields exist in your model.
        if hasattr(item, "reviewed_by"):
            item.reviewed_by = current_user.id

        if hasattr(item, "review_notes"):
            item.review_notes = review_notes

        db.commit()
        db.refresh(item)

        return {
            "message": "Suspicious transaction review updated successfully",
            "id": item.id,
            "transaction_id": item.transaction_id,
            "risk_level": item.risk_level,
            "status": item.status,
        }

    except Exception:
        db.rollback()
        raise