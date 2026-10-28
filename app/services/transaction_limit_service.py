
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.transaction_ledger import TransactionLedger
from app.models.transaction_limit import TransactionLimit


def validate_transaction_limit(
    db: Session,
    transaction_type: str,
    amount: Decimal,
    wallet_id: int,
):
    limit = (
        db.query(TransactionLimit)
        .filter(
            TransactionLimit.transaction_type == transaction_type,
            TransactionLimit.is_active.is_(True),
        )
        .first()
    )

    if limit is None:
        return

    if amount < limit.minimum_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Amount is below the minimum {transaction_type.lower()} limit",
        )

    if amount > limit.maximum_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Amount exceeds the maximum {transaction_type.lower()} limit",
        )

    now = datetime.now(timezone.utc)
    start_of_day = datetime.combine(now.date(), time.min, tzinfo=timezone.utc)

    query = db.query(
        func.coalesce(func.sum(TransactionLedger.amount), 0)
    ).filter(
        TransactionLedger.wallet_id == wallet_id,
        TransactionLedger.transaction_type == transaction_type,
        TransactionLedger.created_at >= start_of_day,
        TransactionLedger.created_at < start_of_day + timedelta(days=1),
    )

    if transaction_type == "TRANSFER":
        query = query.filter(TransactionLedger.description == "Transfer sent")

    daily_total = query.scalar()

    if Decimal(str(daily_total)) + amount > limit.daily_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Daily {transaction_type.lower()} limit exceeded",
        )
