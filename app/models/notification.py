
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Notification(Base):
    __tablename__ = "notifications"

    __table_args__ = (
        CheckConstraint(
            "notification_type IN ('TRANSACTION', 'SECURITY', 'ACCOUNT', 'SYSTEM')",
            name="ck_notification_type_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )

    title: Mapped[str] = mapped_column(
        String(150)
    )

    message: Mapped[str] = mapped_column(
        Text
    )

    notification_type: Mapped[str] = mapped_column(
        String(50)
    )

    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

