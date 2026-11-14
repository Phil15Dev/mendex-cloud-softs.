from typing import Optional

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

service_category_links = Table(
    "service_category_links", Base.metadata,
    Column("service_id", ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
    Column("category_id", ForeignKey("service_categories.id", ondelete="CASCADE"), primary_key=True),
)


class ServiceCategory(Base):
    __tablename__ = "service_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    sort: Mapped[int] = mapped_column(Integer, default=0)


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(60), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(300), default="")
    price: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # KSh; None = ask for quote
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)

    categories: Mapped[list[ServiceCategory]] = relationship(secondary=service_category_links, lazy="selectin",
                                                             order_by="ServiceCategory.sort")

    @property
    def category_slugs(self) -> list[str]:
        return [c.slug for c in self.categories]
