
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies.rbac import require_roles
from app.models.transaction import Transaction
from app.models.wallet import Wallet
from app.models.wallet_balance import WalletBalance
from app.models.user import User
from app.routers.auth import get_current_user, get_db
from app.services.audit_log_service import create_audit_log

router = APIRouter(prefix="/wallets", tags=["Wallets"])


ALLOWED_STATUS_TRANSITIONS = {
    "ACTIVE": {"FROZEN", "SUSPENDED"},
    "FROZEN": {"ACTIVE", "SUSPENDED", "CLOSED"},
    "SUSPENDED": {"ACTIVE", "FROZEN"},
    "CLOSED": set(),
}


@router.get("/me")
def get_my_wallets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(Wallet)
        .filter(Wallet.user_id == current_user.id)
        .all()
    )


@router.post("/")
def create_wallet(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing_wallet = (
        db.query(Wallet)
        .filter(
            Wallet.user_id == current_user.id,
            Wallet.currency == "INR",
        )
        .first()
    )

    if existing_wallet:
        raise HTTPException(
            status_code=409,
            detail="You already have an INR wallet",
        )

    try:
        wallet = Wallet(
            user_id=current_user.id,
            currency="INR",
            status="ACTIVE",
        )
        db.add(wallet)
        db.flush()

        balance = WalletBalance(
            wallet_id=wallet.id,
            available_balance=0,
            pending_balance=0,
        )
        db.add(balance)

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="WALLET_CREATED",
            entity_type="WALLET",
            entity_id=wallet.id,
            details={
                "currency": wallet.currency,
                "status": wallet.status,
            },
        )

        db.commit()
        db.refresh(wallet)

    except Exception:
        db.rollback()
        raise

    return {
        "id": wallet.id,
        "user_id": wallet.user_id,
        "currency": wallet.currency,
        "status": wallet.status,
        "available_balance": "0.00",
        "pending_balance": "0.00",
    }


@router.get("/{wallet_id}/balance")
def get_wallet_balance(
    wallet_id: int,
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
            status_code=404,
            detail="Wallet not found",
        )

    balance = (
        db.query(WalletBalance)
        .filter(WalletBalance.wallet_id == wallet.id)
        .first()
    )

    if balance is None:
        raise HTTPException(
            status_code=404,
            detail="Wallet balance not found",
        )

    return {
        "wallet_id": wallet.id,
        "currency": wallet.currency,
        "available_balance": str(balance.available_balance),
        "pending_balance": str(balance.pending_balance),
    }


@router.patch("/{wallet_id}/status")
def update_wallet_status(
    wallet_id: int,
    new_status: str,
    current_user: User = Depends(
        require_roles("Super Admin", "Admin")
    ),
    db: Session = Depends(get_db),
):
    new_status = new_status.strip().upper()

    if new_status not in ALLOWED_STATUS_TRANSITIONS:
        raise HTTPException(
            status_code=400,
            detail="Invalid wallet status",
        )

    try:
        wallet = (
            db.query(Wallet)
            .filter(Wallet.id == wallet_id)
            .with_for_update()
            .first()
        )

        if wallet is None:
            raise HTTPException(
                status_code=404,
                detail="Wallet not found",
            )

        if wallet.status == new_status:
            raise HTTPException(
                status_code=400,
                detail=f"Wallet is already {new_status}",
            )

        previous_status = wallet.status
        allowed_next_statuses = ALLOWED_STATUS_TRANSITIONS[
            previous_status
        ]

        if new_status not in allowed_next_statuses:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot change wallet status from "
                    f"{previous_status} to {new_status}"
                ),
            )

        wallet.status = new_status

        create_audit_log(
            db=db,
            user_id=current_user.id,
            action="WALLET_STATUS_CHANGED",
            entity_type="WALLET",
            entity_id=wallet.id,
            details={
                "previous_status": previous_status,
                "new_status": new_status,
            },
        )

        db.commit()
        db.refresh(wallet)

        return {
            "wallet_id": wallet.id,
            "user_id": wallet.user_id,
            "currency": wallet.currency,
            "status": wallet.status,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@router.get("/{wallet_id}/transactions")
def get_wallet_transactions(
    wallet_id: int,
    transaction_type: str | None = None,
    transaction_status: str | None = None,
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
            status_code=404,
            detail="Wallet not found",
        )

    query = db.query(Transaction).filter(
        Transaction.wallet_id == wallet.id
    )

    if transaction_type:
        query = query.filter(
            Transaction.transaction_type == transaction_type.strip().upper()
        )

    if transaction_status:
        query = query.filter(
            Transaction.status == transaction_status.strip().upper()
        )

    total = query.count()

    transactions = (
        query.order_by(Transaction.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return {
        "wallet_id": wallet.id,
        "total": total,
        "limit": limit,
        "offset": offset,
        "transactions": [
            {
                "id": transaction.id,
                "transaction_type": transaction.transaction_type,
                "amount": str(transaction.amount),
                "currency": transaction.currency,
                "status": transaction.status,
                "reference_number": transaction.reference_number,
            }
            for transaction in transactions
        ],
    }
