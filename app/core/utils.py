import math
import re
import secrets
from dataclasses import dataclass
from typing import Any, List

from sqlalchemy import func, select


def normalize_phone(raw: str) -> str:
    """Kenyan number as 2547XXXXXXXX / 2541XXXXXXXX, or ValueError."""
    d = re.sub(r"\D", "", raw or "")
    if len(d) == 13 and d.startswith("2540"):  # "+254 0712 345 678": country code plus the leading 0
        d = "254" + d[4:]
    if len(d) == 10 and d.startswith("0"):
        d = "254" + d[1:]
    elif len(d) == 9 and d[0] in "17":
        d = "254" + d
    if not re.fullmatch(r"254[17]\d{8}", d):
        raise ValueError("Enter a valid Kenyan phone number, e.g. 0712 345 678.")
    return d


def new_request_code() -> str:
    return "MM-" + secrets.token_hex(3).upper()


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:50] or "item"


def to_int(raw: str):
    digits = "".join(c for c in (raw or "") if c.isdigit())
    return int(digits) if digits else None


@dataclass
class Page:
    items: List[Any]
    page: int
    pages: int
    total: int
    per_page: int

    @property
    def has_prev(self): return self.page > 1
    @property
    def has_next(self): return self.page < self.pages


def paginate(db, stmt, page: int = 1, per_page: int = 20, rows: bool = False) -> Page:
    page = max(1, page or 1)
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    pages = max(1, math.ceil(total / per_page))
    page = min(page, pages)
    paged = stmt.limit(per_page).offset((page - 1) * per_page)
    items = db.execute(paged).all() if rows else db.scalars(paged).all()
    return Page(items, page, pages, total, per_page)


def utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)


def phone_search_terms(q: str) -> list:
    """Phone patterns for a search box: numbers are stored as 2547XXXXXXXX, but people type 0712 345 678."""
    digits = re.sub(r"\D", "", q or "")
    if len(digits) < 3:
        return []
    if digits.startswith("2540"):
        digits = "254" + digits[4:]
    return [digits, "254" + digits[1:]] if digits.startswith("0") else [digits]
