
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.refund import Refund
from app.models.transaction import Transaction
from app.models.transaction_ledger import TransactionLedger
from app.models.user import User
from app.models.wallet import Wallet
from app.models.wallet_balance import WalletBalance
from app.services.audit_log_service import create_audit_log
from app.services.notification_service import create_notification
from app.services.suspicious_transaction_service import (
    check_suspicious_transaction,
)
from app.services.transaction_limit_service import validate_transaction_limit
from app.services.wallet_service import validate_wallet_is_active


def create_refund(
    db: Session,
    transaction_id: int,
    amount: Decimal,
    current_user: User,
):
    if not amount.is_finite() or amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refund amount must be greater than zero",
        )

    try:
        original_transaction = (
            db.query(Transaction)
            .join(Wallet, Transaction.wallet_id == Wallet.id)
            .filter(
                Transaction.id == transaction_id,
                Wallet.user_id == current_user.id,
            )
            .with_for_update()
            .first()
        )

        if original_transaction is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transaction not found",
            )

        if original_transaction.status != "COMPLETED":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only completed transactions can be refunded",
            )

        if original_transaction.transaction_type != "DEPOSIT":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only deposit transactions can be refunded",
            )

        wallet = (
            db.query(Wallet)
            .filter(Wallet.id == original_transaction.wallet_id)
            .with_for_update()
            .first()
        )

        if wallet is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet not found",
            )

        validate_wallet_is_active(wallet)

        if amount > original_transaction.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Refund amount cannot exceed the original transaction amount",
            )

        existing_refunds = (
            db.query(Refund)
            .filter(
                Refund.transaction_id == original_transaction.id,
                Refund.status.in_(["PENDING", "PROCESSING", "COMPLETED"]),
            )
            .with_for_update()
            .all()
        )

        already_refunded = sum(
            (refund.amount for refund in existing_refunds),
            Decimal("0.00"),
        )

        if already_refunded + amount > original_transaction.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Total refunds cannot exceed the original transaction amount",
            )

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

        if balance.available_balance < amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance for refund",
            )

        validate_transaction_limit(
            db=db,
            transaction_type="REFUND",
            amount=amount,
            wallet_id=wallet.id,
        )

        before = balance.available_balance
        after = before - amount

        refund = Refund(
            transaction_id=original_transaction.id,
            wallet_id=wallet.id,
            amount=amount,
            status="COMPLETED",
            reference_number=f"REF-{uuid4().hex}",
        )
        db.add(refund)
        db.flush()

        refund_transaction = Transaction(
            wallet_id=wallet.id,
            transaction_type="REFUND",
            amount=amount,
            currency=original_transaction.currency,
            status="COMPLETED",
            reference_number=f"REF-TXN-{refund.id}",
        )
        db.add(refund_transaction)
        db.flush()

        # Check whether the refund needs security review.
        check_suspicious_transaction(
            db=db,
            transaction=refund_transaction,
        )

        db.add(
            TransactionLedger(
                wallet_id=wallet.id,
                transaction_type="REFUND",
                amount=amount,
                balance_before=before,
                balance_after=after,
                reference_entity="REFUND",
                reference_id=refund.id,
                description="Refund processed",
            )
        )

        balance.available_balance = after

        # Notify the user that the refund was completed.
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Refund Successful",
            message=(
                f"Your refund of {amount} "
                f"{original_transaction.currency} "
                "has been processed successfully."
            ),
            notification_type="TRANSACTION",
        )

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="REFUND_COMPLETED",
            entity_type="REFUND",
            entity_id=refund.id,
            details={
                "original_transaction_id": original_transaction.id,
                "refund_transaction_id": refund_transaction.id,
                "wallet_id": wallet.id,
                "amount": str(amount),
                "currency": original_transaction.currency,
                "previous_balance": str(before),
                "new_balance": str(after),
                "reference_number": refund.reference_number,
                "status": refund.status,
            },
        )

        db.commit()
        db.refresh(refund)
        db.refresh(balance)

        return {
            "id": refund.id,
            "transaction_id": refund.transaction_id,
            "wallet_id": refund.wallet_id,
            "amount": str(refund.amount),
            "status": refund.status,
            "reference_number": refund.reference_number,
            "available_balance": str(balance.available_balance),
        }

    except Exception:
        db.rollback()
        raise
