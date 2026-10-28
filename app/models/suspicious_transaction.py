
from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class SuspiciousTransaction(Base):
    __tablename__ = "suspicious_transactions"

    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')",
            name="ck_suspicious_transaction_risk_level_valid",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'UNDER_REVIEW', 'APPROVED', 'REJECTED')",
            name="ck_suspicious_transaction_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    transaction_id: Mapped[int] = mapped_column(
        ForeignKey("transactions.id")
    )

    reason: Mapped[str] = mapped_column(Text)

    risk_level: Mapped[str] = mapped_column(
        String(20),
        default="MEDIUM",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDING",
    )

    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    review_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )