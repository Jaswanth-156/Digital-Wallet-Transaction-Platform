
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.models.wallet import Wallet
from app.models.wallet_balance import WalletBalance
from app.models.user import User
from app.routers.auth import get_current_user, get_db

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary")
def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallets = (
        db.query(Wallet)
        .filter(Wallet.user_id == current_user.id)
        .all()
    )

    wallet_ids = [wallet.id for wallet in wallets]

    balances = []
    transactions = []

    if wallet_ids:
        balances = (
            db.query(WalletBalance)
            .filter(WalletBalance.wallet_id.in_(wallet_ids))
            .all()
        )

        transactions = (
            db.query(Transaction)
            .filter(Transaction.wallet_id.in_(wallet_ids))
            .order_by(Transaction.id.desc())
            .limit(10)
            .all()
        )

    balance_by_wallet = {
        balance.wallet_id: balance for balance in balances
    }

    total_available_balance = sum(
        (
            balance.available_balance
            for balance in balances
        ),
        Decimal("0.00"),
    )

    total_pending_balance = sum(
        (
            balance.pending_balance
            for balance in balances
        ),
        Decimal("0.00"),
    )

    wallet_details = [
        {
            "wallet_id": wallet.id,
            "currency": wallet.currency,
            "status": wallet.status,
            "available_balance": str(
                balance_by_wallet[wallet.id].available_balance
                if wallet.id in balance_by_wallet
                else Decimal("0.00")
            ),
            "pending_balance": str(
                balance_by_wallet[wallet.id].pending_balance
                if wallet.id in balance_by_wallet
                else Decimal("0.00")
            ),
        }
        for wallet in wallets
    ]

    recent_transactions = [
        {
            "id": transaction.id,
            "wallet_id": transaction.wallet_id,
            "transaction_type": transaction.transaction_type,
            "amount": str(transaction.amount),
            "currency": transaction.currency,
            "status": transaction.status,
            "reference_number": transaction.reference_number,
        }
        for transaction in transactions
    ]

    return {
        "wallet_count": len(wallets),
        "total_available_balance": str(total_available_balance),
        "total_pending_balance": str(total_pending_balance),
        "wallets": wallet_details,
        "recent_transactions": recent_transactions,
    }
