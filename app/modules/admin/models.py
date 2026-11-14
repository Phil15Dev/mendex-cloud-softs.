from datetime import datetime
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.utils import utcnow

role_permissions = Table(
    "role_permissions", Base.metadata,
    Column("role_id", ForeignKey("admin_roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(60), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")


class AdminRole(Base):
    __tablename__ = "admin_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)
    description: Mapped[str] = mapped_column(String(200), default="")
    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")


class AdminAuditLog(Base):
    """Append-only record of security-relevant and money-related actions."""
    __tablename__ = "admin_audit_log"
    __table_args__ = (Index("ix_admin_audit_log_created_at", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[Optional[int]] = mapped_column(ForeignKey("admin_accounts.id", ondelete="SET NULL"), nullable=True)
    actor: Mapped[str] = mapped_column(String(80), default="")  # name kept even if the account is removed
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(40), default="")
    target_id: Mapped[str] = mapped_column(String(40), default="")
    detail: Mapped[str] = mapped_column(Text, default="")
    ip: Mapped[str] = mapped_column(String(45), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
