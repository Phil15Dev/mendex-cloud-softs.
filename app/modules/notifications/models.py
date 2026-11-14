from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.utils import utcnow


class Notification(Base):
    """In-app alert for the admin team (for example a new customer request)."""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(String(300))
    request_id: Mapped[Optional[int]] = mapped_column(ForeignKey("service_requests.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailLog(Base):
    """Every email the system tried to send (never stores reset links)."""
    __tablename__ = "email_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_address: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(12))  # sent | failed | logged
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
