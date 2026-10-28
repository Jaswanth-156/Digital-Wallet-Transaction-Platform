
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Refund(Base):
    __tablename__ = "refunds"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_refund_amount_positive",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_refund_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id")
    )

    wallet_id: Mapped[int] = mapped_column(
        ForeignKey("wallets.id")
    )

    amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2)
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
    )

    reference_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
    )