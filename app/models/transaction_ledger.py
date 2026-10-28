
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TransactionLedger(Base):
    __tablename__ = "transaction_ledger"

    __table_args__ = (
        CheckConstraint(
            "amount > 0",
            name="ck_ledger_amount_positive",
        ),
        CheckConstraint(
            "balance_before >= 0",
            name="ck_ledger_balance_before_nonnegative",
        ),
        CheckConstraint(
            "balance_after >= 0",
            name="ck_ledger_balance_after_nonnegative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"))
    transaction_type: Mapped[str] = mapped_column(String(30))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    reference_entity: Mapped[str] = mapped_column(String(50))
    reference_id: Mapped[int]
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
