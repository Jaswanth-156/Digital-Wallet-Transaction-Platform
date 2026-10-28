
from fastapi import HTTPException, status

from app.models.wallet import Wallet


def validate_wallet_is_active(wallet: Wallet) -> None:
    if wallet.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Wallet is not active",
        )
