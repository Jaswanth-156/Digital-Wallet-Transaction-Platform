
from decimal import Decimal

from sqlalchemy import CheckConstraint, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TransactionLimit(Base):
    __tablename__ = "transaction_limits"

    __table_args__ = (
        CheckConstraint(
            "minimum_amount > 0",
            name="ck_transaction_limit_minimum_positive",
        ),
        CheckConstraint(
            "maximum_amount >= minimum_amount",
            name="ck_transaction_limit_maximum_gte_minimum",
        ),
        CheckConstraint(
            "daily_limit > 0",
            name="ck_transaction_limit_daily_positive",
        ),
        CheckConstraint(
            "transaction_type IN ('DEPOSIT', 'WITHDRAWAL', 'TRANSFER', 'REFUND')",
            name="ck_transaction_limit_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    transaction_type: Mapped[str] = mapped_column(
        String(30),
        unique=True,
    )

    minimum_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
        default=Decimal("1.00"),
    )

    maximum_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
    )

    daily_limit: Mapped[Decimal] = mapped_column(
        Numeric(18, 2),
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
    )