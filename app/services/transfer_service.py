
import hashlib
import json
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.idempotency_key import IdempotencyKey
from app.models.transaction import Transaction
from app.models.transaction_ledger import TransactionLedger
from app.models.transfer import Transfer
from app.models.user import User
from app.repositories.transfer_repository import (
    get_wallets_for_update,
    get_wallet_balance_for_update,
)
from app.services.audit_log_service import create_audit_log
from app.services.notification_service import create_notification
from app.services.suspicious_transaction_service import (
    check_suspicious_transaction,
)
from app.services.transaction_limit_service import validate_transaction_limit
from app.services.wallet_service import validate_wallet_is_active


def create_transfer(
    db: Session,
    sender_wallet_id: int,
    receiver_wallet_id: int,
    amount: Decimal,
    current_user: User,
    idempotency_key: str | None = None,
):
    if not amount.is_finite() or amount <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transfer amount must be greater than zero",
        )

    if idempotency_key is not None:
        idempotency_key = idempotency_key.strip()

        if not idempotency_key or len(idempotency_key) > 255:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Idempotency key must contain 1 to 255 characters",
            )

    if sender_wallet_id == receiver_wallet_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot transfer to the same wallet",
        )

    request_hash = hashlib.sha256(
        json.dumps(
            {
                "sender_wallet_id": sender_wallet_id,
                "receiver_wallet_id": receiver_wallet_id,
                "amount": str(amount),
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()

    if idempotency_key is not None:
        existing_key = (
            db.query(IdempotencyKey)
            .filter(
                IdempotencyKey.user_id == current_user.id,
                IdempotencyKey.key == idempotency_key,
            )
            .first()
        )

        if existing_key:
            if existing_key.request_hash != request_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key was already used for a different request",
                )

            if existing_key.response_data:
                return json.loads(existing_key.response_data)

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Request with this idempotency key is still processing",
            )

    try:
        if idempotency_key is not None:
            idempotency_record = IdempotencyKey(
                user_id=current_user.id,
                key=idempotency_key,
                request_hash=request_hash,
                response_data=None,
            )
            db.add(idempotency_record)

            try:
                db.flush()
            except IntegrityError:
                db.rollback()

                existing_key = (
                    db.query(IdempotencyKey)
                    .filter(
                        IdempotencyKey.user_id == current_user.id,
                        IdempotencyKey.key == idempotency_key,
                    )
                    .first()
                )

                if existing_key:
                    if existing_key.request_hash != request_hash:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Idempotency key was already used for a different request",
                        )

                    if existing_key.response_data:
                        return json.loads(existing_key.response_data)

                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Request with this idempotency key could not be completed; retry shortly",
                )

        wallets = get_wallets_for_update(
            db,
            [sender_wallet_id, receiver_wallet_id],
        )
        wallets_by_id = {wallet.id: wallet for wallet in wallets}

        sender = wallets_by_id.get(sender_wallet_id)
        receiver = wallets_by_id.get(receiver_wallet_id)

        if sender is None or sender.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sender wallet not found",
            )

        if receiver is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Receiver wallet not found",
            )

        validate_wallet_is_active(sender)
        validate_wallet_is_active(receiver)

        if sender.currency != receiver.currency:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Wallet currencies must match",
            )

        balances = {}

        for wallet_id in sorted([sender.id, receiver.id]):
            balance = get_wallet_balance_for_update(db, wallet_id)

            if balance is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Wallet balance not found",
                )

            balances[wallet_id] = balance

        sender_balance = balances[sender.id]
        receiver_balance = balances[receiver.id]

        if amount > sender_balance.available_balance:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance",
            )

        validate_transaction_limit(
            db=db,
            transaction_type="TRANSFER",
            amount=amount,
            wallet_id=sender.id,
        )

        sender_before = sender_balance.available_balance
        receiver_before = receiver_balance.available_balance

        sender_after = sender_before - amount
        receiver_after = receiver_before + amount

        transfer = Transfer(
            sender_wallet_id=sender.id,
            receiver_wallet_id=receiver.id,
            amount=amount,
            currency=sender.currency,
            status="COMPLETED",
            reference_number=f"TRF-{uuid4().hex}",
        )
        db.add(transfer)
        db.flush()

        sender_transaction = Transaction(
            wallet_id=sender.id,
            transaction_type="TRANSFER",
            amount=amount,
            currency=sender.currency,
            status="COMPLETED",
            reference_number=f"TRF-OUT-{transfer.id}",
        )

        receiver_transaction = Transaction(
            wallet_id=receiver.id,
            transaction_type="TRANSFER",
            amount=amount,
            currency=receiver.currency,
            status="COMPLETED",
            reference_number=f"TRF-IN-{transfer.id}",
        )

        db.add_all([sender_transaction, receiver_transaction])
        db.flush()


        check_suspicious_transaction(
            db=db,
            transaction=sender_transaction,
        )

        check_suspicious_transaction(
            db=db,
            transaction=receiver_transaction,
        )

        db.add_all(
            [
                TransactionLedger(
                    wallet_id=sender.id,
                    transaction_type="TRANSFER",
                    amount=amount,
                    balance_before=sender_before,
                    balance_after=sender_after,
                    reference_entity="TRANSFER",
                    reference_id=transfer.id,
                    description="Transfer sent",
                ),
                TransactionLedger(
                    wallet_id=receiver.id,
                    transaction_type="TRANSFER",
                    amount=amount,
                    balance_before=receiver_before,
                    balance_after=receiver_after,
                    reference_entity="TRANSFER",
                    reference_id=transfer.id,
                    description="Transfer received",
                ),
            ]
        )

        sender_balance.available_balance = sender_after
        receiver_balance.available_balance = receiver_after


        create_notification(
            db=db,
            user_id=current_user.id,
            title="Transfer Sent",
            message=(
                f"Your transfer of {amount} {sender.currency} "
                f"to wallet {receiver.id} was completed successfully."
            ),
            notification_type="TRANSACTION",
        )

        create_notification(
            db=db,
            user_id=receiver.user_id,
            title="Transfer Received",
            message=(
                f"You received {amount} {receiver.currency} "
                f"from wallet {sender.id}."
            ),
            notification_type="TRANSACTION",
        )


        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="TRANSFER_COMPLETED",
            entity_type="TRANSFER",
            entity_id=transfer.id,
            details={
                "sender_wallet_id": sender.id,
                "receiver_wallet_id": receiver.id,
                "amount": str(amount),
                "currency": transfer.currency,
                "sender_previous_balance": str(sender_before),
                "sender_new_balance": str(sender_after),
                "receiver_previous_balance": str(receiver_before),
                "receiver_new_balance": str(receiver_after),
                "reference_number": transfer.reference_number,
                "sender_transaction_id": sender_transaction.id,
                "receiver_transaction_id": receiver_transaction.id,
            },
        )

        response = {
            "transfer_id": transfer.id,
            "sender_wallet_id": sender.id,
            "receiver_wallet_id": receiver.id,
            "amount": str(amount),
            "currency": transfer.currency,
            "status": transfer.status,
            "sender_balance": str(sender_after),
            "receiver_balance": str(receiver_after),
        }

        if idempotency_key is not None:
            idempotency_record.response_data = json.dumps(response)


        db.commit()

        return response

    except Exception:
        db.rollback()
        raise
