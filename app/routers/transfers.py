
from decimal import Decimal

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.transfer import Transfer
from app.models.user import User
from app.models.wallet import Wallet
from app.routers.auth import get_current_user
from app.services.transfer_service import create_transfer


router = APIRouter(prefix="/transfers", tags=["Transfers"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/")
def transfer_money(
    sender_wallet_id: int,
    receiver_wallet_id: int,
    amount: Decimal,
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not amount.is_finite():
        raise HTTPException(
            status_code=400,
            detail="Transfer amount must be a valid number",
        )

    return create_transfer(
        db=db,
        sender_wallet_id=sender_wallet_id,
        receiver_wallet_id=receiver_wallet_id,
        amount=amount,
        current_user=current_user,
        idempotency_key=idempotency_key,
    )


@router.get("/me")
def get_my_transfers(
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 100",
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset cannot be negative",
        )

    query = (
        db.query(Transfer)
        .join(
            Wallet,
            or_(
                Transfer.sender_wallet_id == Wallet.id,
                Transfer.receiver_wallet_id == Wallet.id,
            ),
        )
        .filter(Wallet.user_id == current_user.id)
        .distinct()
    )

    total = query.count()

    transfers = (
        query.order_by(Transfer.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "transfers": transfers,
    }
