
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.deposit import Deposit
from app.models.transaction import Transaction
from app.models.transaction_ledger import TransactionLedger
from app.models.wallet import Wallet
from app.models.user import User
from app.models.wallet_balance import WalletBalance
from app.routers.auth import get_current_user
from app.services.audit_log_service import create_audit_log
from app.services.notification_service import create_notification
from app.services.suspicious_transaction_service import (
    check_suspicious_transaction,
)
from app.services.transaction_limit_service import validate_transaction_limit
from app.services.wallet_service import validate_wallet_is_active


router = APIRouter(prefix="/deposits", tags=["Deposits"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/")
def create_deposit(
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
            detail="Deposit amount must be greater than zero",
        )

    validate_transaction_limit(
        db=db,
        transaction_type="DEPOSIT",
        amount=amount,
        wallet_id=wallet.id,
    )

    deposit = Deposit(
        wallet_id=wallet.id,
        amount=amount,
        currency=wallet.currency,
        status="PENDING",
        reference_number=f"DEP-{uuid4().hex}",
    )

    try:
        db.add(deposit)
        db.flush()

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="DEPOSIT_CREATED",
            entity_type="DEPOSIT",
            entity_id=deposit.id,
            details={
                "wallet_id": wallet.id,
                "amount": str(deposit.amount),
                "currency": deposit.currency,
                "status": deposit.status,
                "reference_number": deposit.reference_number,
            },
        )

        db.commit()
        db.refresh(deposit)

    except Exception:
        db.rollback()
        raise

    return {
        "id": deposit.id,
        "wallet_id": deposit.wallet_id,
        "amount": str(deposit.amount),
        "currency": deposit.currency,
        "status": deposit.status,
        "reference_number": deposit.reference_number,
    }


@router.post("/{deposit_id}/complete")
def complete_deposit(
    deposit_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deposit = (
        db.query(Deposit)
        .join(Wallet, Deposit.wallet_id == Wallet.id)
        .filter(
            Deposit.id == deposit_id,
            Wallet.user_id == current_user.id,
        )
        .with_for_update(of=Deposit)
        .first()
    )

    if deposit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Deposit not found",
        )

    if deposit.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Deposit is not pending",
        )

    wallet = (
        db.query(Wallet)
        .filter(Wallet.id == deposit.wallet_id)
        .with_for_update()
        .first()
    )

    if wallet is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Wallet not found",
        )

    validate_wallet_is_active(wallet)

    try:
        balance = (
            db.query(WalletBalance)
            .filter(WalletBalance.wallet_id == wallet.id)
            .with_for_update()
            .first()
        )

        if balance is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet balance not found",
            )

        validate_transaction_limit(
            db=db,
            transaction_type="DEPOSIT",
            amount=deposit.amount,
            wallet_id=wallet.id,
        )

        before = balance.available_balance
        after = before + deposit.amount

        transaction = Transaction(
            wallet_id=wallet.id,
            transaction_type="DEPOSIT",
            amount=deposit.amount,
            currency=deposit.currency,
            status="COMPLETED",
            reference_number=deposit.reference_number,
        )
        db.add(transaction)
        db.flush()

        # Check whether this deposit needs security review.
        check_suspicious_transaction(
            db=db,
            transaction=transaction,
        )

        ledger = TransactionLedger(
            wallet_id=wallet.id,
            transaction_type="DEPOSIT",
            amount=deposit.amount,
            balance_before=before,
            balance_after=after,
            reference_entity="DEPOSIT",
            reference_id=deposit.id,
            description="Deposit completed",
        )
        db.add(ledger)

        balance.available_balance = after
        deposit.status = "COMPLETED"

        # Notify the user that the deposit was completed.
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Deposit Successful",
            message=(
                f"Your deposit of {deposit.amount} "
                f"{deposit.currency} has been completed successfully."
            ),
            notification_type="TRANSACTION",
        )

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="DEPOSIT_COMPLETED",
            entity_type="DEPOSIT",
            entity_id=deposit.id,
            details={
                "wallet_id": wallet.id,
                "transaction_id": transaction.id,
                "amount": str(deposit.amount),
                "currency": deposit.currency,
                "previous_balance": str(before),
                "new_balance": str(after),
                "reference_number": deposit.reference_number,
            },
        )

        db.commit()
        db.refresh(deposit)
        db.refresh(balance)

        return {
            "deposit_id": deposit.id,
            "transaction_id": transaction.id,
            "wallet_id": wallet.id,
            "amount": str(deposit.amount),
            "currency": deposit.currency,
            "status": deposit.status,
            "available_balance": str(balance.available_balance),
        }

    except Exception:
        db.rollback()
        raise
