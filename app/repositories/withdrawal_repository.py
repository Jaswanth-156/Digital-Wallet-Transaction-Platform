
from sqlalchemy.orm import Session

from app.models.withdrawal import Withdrawal
from app.models.wallet import Wallet
from app.models.wallet_balance import WalletBalance


def get_withdrawal_for_user(
    db: Session,
    withdrawal_id: int,
    user_id: int,
) -> Withdrawal | None:
    return (
        db.query(Withdrawal)
        .join(Wallet, Withdrawal.wallet_id == Wallet.id)
        .filter(
            Withdrawal.id == withdrawal_id,
            Wallet.user_id == user_id,
        )
        .with_for_update(of=Withdrawal)
        .first()
    )


def get_wallet_balance_for_update(
    db: Session,
    wallet_id: int,
) -> WalletBalance | None:
    return (
        db.query(WalletBalance)
        .filter(WalletBalance.wallet_id == wallet_id)
        .with_for_update()
        .first()
    )


def save_withdrawal(
    db: Session,
    withdrawal: Withdrawal,
) -> Withdrawal:
    db.add(withdrawal)
    return withdrawal
