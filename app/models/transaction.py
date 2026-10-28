
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Transaction(Base):
    __tablename__ = "transactions"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_transaction_amount_positive",
        ),
        CheckConstraint(
            "transaction_type IN ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER', 'REFUND', 'FEE', 'ADJUSTMENT', 'REVERSAL')",
            name="ck_transaction_type_valid",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED')",
            name="ck_transaction_status_valid",
        ),
        CheckConstraint(
            "currency = upper(currency)",
            name="ck_transaction_currency_uppercase",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"))
    transaction_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    reference_number: Mapped[str] = mapped_column(
        String(100),
        unique=True,
    )
