
from sqlalchemy.orm import Session

from app.models.wallet import Wallet
from app.models.wallet_balance import WalletBalance


def get_wallets_for_update(
    db: Session,
    wallet_ids: list[int],
) -> list[Wallet]:
    return (
        db.query(Wallet)
        .filter(Wallet.id.in_(wallet_ids))
        .order_by(Wallet.id)
        .with_for_update()
        .all()
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
