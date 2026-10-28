
from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Wallet(Base):
    __tablename__ = "wallets"

    __table_args__ = (
        CheckConstraint(
            "status IN ('ACTIVE', 'FROZEN', 'SUSPENDED', 'CLOSED')",
            name="ck_wallet_status_valid",
        ),
        CheckConstraint(
            "currency = upper(currency)",
            name="ck_wallet_currency_uppercase",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
