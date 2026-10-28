
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Transfer(Base):
    __tablename__ = "transfers"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_transfer_amount_positive",
        ),
        CheckConstraint(
            "sender_wallet_id <> receiver_wallet_id",
            name="ck_transfer_different_wallets",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_transfer_status_valid",
        ),
        CheckConstraint(
            "currency = upper(currency)",
            name="ck_transfer_currency_uppercase",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    sender_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id")
    )
    receiver_wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id")
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    reference_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
    )
