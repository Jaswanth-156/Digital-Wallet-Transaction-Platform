
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.transaction_ledger import TransactionLedger
from app.models.user import User
from app.models.wallet import Wallet
from app.repositories.withdrawal_repository import (
    get_withdrawal_for_user,
    get_wallet_balance_for_update,
)
from app.services.audit_log_service import create_audit_log
from app.services.notification_service import create_notification
from app.services.suspicious_transaction_service import (
    check_suspicious_transaction,
)
from app.services.transaction_limit_service import validate_transaction_limit
from app.services.wallet_service import validate_wallet_is_active


def complete_withdrawal(db: Session, withdrawal_id: int, current_user: User):
    withdrawal = get_withdrawal_for_user(db, withdrawal_id, current_user.id)

    if withdrawal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Withdrawal not found",
        )

    if withdrawal.status != "PENDING":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Withdrawal is not pending",
        )

    try:
        wallet = (
            db.query(Wallet)
            .filter(
                Wallet.id == withdrawal.wallet_id,
                Wallet.user_id == current_user.id,
            )
            .with_for_update()
            .first()
        )

        if wallet is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet not found",
            )

        validate_wallet_is_active(wallet)

        balance = get_wallet_balance_for_update(db, wallet.id)

        if balance is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Wallet balance not found",
            )

        if withdrawal.amount > balance.available_balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance",
            )

        validate_transaction_limit(
            db=db,
            transaction_type="WITHDRAWAL",
            amount=withdrawal.amount,
            wallet_id=wallet.id,
        )

        before = balance.available_balance
        after = before - withdrawal.amount

        transaction = Transaction(
            wallet_id=wallet.id,
            transaction_type="WITHDRAWAL",
            amount=withdrawal.amount,
            currency=withdrawal.currency,
            status="COMPLETED",
            reference_number=withdrawal.reference_number,
        )
        db.add(transaction)
        db.flush()

        # Check whether the withdrawal needs security review.
        check_suspicious_transaction(
            db=db,
            transaction=transaction,
        )

        ledger = TransactionLedger(
            wallet_id=wallet.id,
            transaction_type="WITHDRAWAL",
            amount=withdrawal.amount,
            balance_before=before,
            balance_after=after,
            reference_entity="WITHDRAWAL",
            reference_id=withdrawal.id,
            description="Withdrawal completed",
        )
        db.add(ledger)

        balance.available_balance = after
        withdrawal.status = "COMPLETED"

        # Notify the user that the withdrawal was completed.
        create_notification(
            db=db,
            user_id=current_user.id,
            title="Withdrawal Successful",
            message=(
                f"Your withdrawal of {withdrawal.amount} "
                f"{withdrawal.currency} has been completed successfully."
            ),
            notification_type="TRANSACTION",
        )

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="WITHDRAWAL_COMPLETED",
            entity_type="WITHDRAWAL",
            entity_id=withdrawal.id,
            details={
                "wallet_id": wallet.id,
                "transaction_id": transaction.id,
                "amount": str(withdrawal.amount),
                "currency": withdrawal.currency,
                "previous_balance": str(before),
                "new_balance": str(after),
                "reference_number": withdrawal.reference_number,
            },
        )

        db.commit()
        db.refresh(balance)
        db.refresh(withdrawal)

        return {
            "withdrawal_id": withdrawal.id,
            "transaction_id": transaction.id,
            "wallet_id": wallet.id,
            "amount": str(withdrawal.amount),
            "currency": withdrawal.currency,
            "status": withdrawal.status,
            "available_balance": str(balance.available_balance),
        }

    except Exception:
        db.rollback()
        raise
