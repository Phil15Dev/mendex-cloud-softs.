from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.utils import utcnow


class ServiceRequest(Base):
    __tablename__ = "service_requests"
    __table_args__ = (Index("ix_service_requests_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id", ondelete="RESTRICT"), index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="RESTRICT"), index=True)
    service_name: Mapped[str] = mapped_column(String(120))  # name when requested
    fee: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # price when requested (history never changes)
    details: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="received", index=True)
    note: Mapped[str] = mapped_column(Text, default="")  # latest message shown to the customer
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    service = relationship("Service", lazy="joined")
    customer = relationship("Customer", lazy="joined")
    history = relationship("RequestStatusHistory", back_populates="request", cascade="all, delete-orphan",
                           order_by="RequestStatusHistory.id", lazy="selectin")


class RequestStatusHistory(Base):
    __tablename__ = "request_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("service_requests.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    to_status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text, default="")
    admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("admin_accounts.id", ondelete="SET NULL"), nullable=True)
    actor: Mapped[str] = mapped_column(String(100), default="Customer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    request = relationship("ServiceRequest", back_populates="history")
