
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class WalletBalance(Base):
    __tablename__ = "wallet_balances"

    __table_args__ = (
        CheckConstraint(
            "available_balance >= 0",
            name="ck_wallet_available_balance_nonnegative",
        ),
        CheckConstraint(
            "pending_balance >= 0",
            name="ck_wallet_pending_balance_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id"),
        unique=True,
    )
    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
    )
    pending_balance: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("0.00"),
    )
