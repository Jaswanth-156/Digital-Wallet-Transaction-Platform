
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.models.wallet import Wallet
from app.models.wallet_balance import WalletBalance
from app.models.withdrawal import Withdrawal
from app.routers.auth import get_current_user
from app.services.audit_log_service import create_audit_log
from app.services.transaction_limit_service import validate_transaction_limit
from app.services.wallet_service import validate_wallet_is_active
from app.services.withdrawal_service import complete_withdrawal


router = APIRouter(prefix="/withdrawals", tags=["Withdrawals"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/")
def create_withdrawal(
    wallet_id: int,
    amount: Decimal,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallet = (
        db.query(Wallet)
        .filter(
            Wallet.id == wallet_id,
            Wallet.user_id == current_user.id,
        )
        .first()
    )

    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    validate_wallet_is_active(wallet)

    if not amount.is_finite() or amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Withdrawal amount must be greater than zero",
        )

    balance = (
        db.query(WalletBalance)
        .filter(WalletBalance.wallet_id == wallet.id)
        .first()
    )

    if balance is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet balance not found",
        )

    if amount > balance.available_balance:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient wallet balance",
        )

    validate_transaction_limit(
        db=db,
        transaction_type="WITHDRAWAL",
        amount=amount,
        wallet_id=wallet.id,
    )

    withdrawal = Withdrawal(
        wallet_id=wallet.id,
        amount=amount,
        currency=wallet.currency,
        status="PENDING",
        reference_number=f"WDR-{uuid4().hex}",
    )

    try:
        db.add(withdrawal)
        db.flush()

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="WITHDRAWAL_CREATED",
            entity_type="WITHDRAWAL",
            entity_id=withdrawal.id,
            details={
                "wallet_id": wallet.id,
                "amount": str(withdrawal.amount),
                "currency": withdrawal.currency,
                "status": withdrawal.status,
                "reference_number": withdrawal.reference_number,
            },
        )

        db.commit()
        db.refresh(withdrawal)

    except Exception:
        db.rollback()
        raise

    return {
        "id": withdrawal.id,
        "wallet_id": withdrawal.wallet_id,
        "amount": str(withdrawal.amount),
        "currency": withdrawal.currency,
        "status": withdrawal.status,
        "reference_number": withdrawal.reference_number,
    }


@router.post("/{withdrawal_id}/complete")
def complete_withdrawal_endpoint(
    withdrawal_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return complete_withdrawal(
        db=db,
        withdrawal_id=withdrawal_id,
        current_user=current_user,
    )
