from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import CATEGORIES
from app.core.utils import slugify

from .models import Service, ServiceCategory

SEED = [  # slug, name, description, categories, price (KSh; None = ask for quote)
    ("helb", "HELB Scholarship", "Scholarship application support.", ["government", "education"], 1000),
    ("kra-itax", "KRA", "Help with KRA online services.", ["government"], 200),
    ("ntsa", "NTSA", "Support with NTSA online services.", ["government"], 600),
    ("kuccps", "KUCCPS", "KUCCPS application support.", ["government"], 800),
    ("passport", "Passport applications", "Guidance through passport applications.", ["government"], 1000),
    ("scholarships", "Scholarships", "Find and apply for local and international scholarships.", ["education"], 1000),
    ("ecitizen", "eCitizen services", "Account setup and government service applications.", ["government"], None),
    ("payslips", "Online payslips", "Download your government payslip online.", ["online"], None),
    ("tsc", "TSC services", "TSC number, account and online service help.", ["online"], 350),
    ("nhif-sha", "NHIF / SHA", "SHA registration, updates and contributions help.", ["online"], 350),
    ("helb-docs", "HELB support documents", "Help preparing the documents HELB asks for.", ["education"], None),
]


def seed_services(db: Session) -> None:
    """Create missing categories and services. Anything already in the database is left exactly as it is."""
    cats = {c.slug: c for c in db.scalars(select(ServiceCategory))}
    for slug, name, sort in CATEGORIES:
        if slug not in cats:
            cats[slug] = ServiceCategory(slug=slug, name=name, sort=sort)
            db.add(cats[slug])
    db.flush()
    have = {s for (s,) in db.execute(select(Service.slug))}
    for i, (slug, name, desc, cat_slugs, price) in enumerate(SEED):
        if slug not in have:
            db.add(Service(slug=slug, name=name, description=desc, price=price, sort=i,
                           categories=[cats[c] for c in cat_slugs]))
    db.commit()


def active_services(db: Session) -> List[Service]:
    return db.scalars(select(Service).where(Service.active.is_(True)).order_by(Service.sort, Service.id)).all()


def all_categories(db: Session) -> List[ServiceCategory]:
    return db.scalars(select(ServiceCategory).order_by(ServiceCategory.sort)).all()


def unique_slug(db: Session, name: str) -> str:
    base, slug, n = slugify(name), slugify(name), 2
    while db.scalar(select(Service.id).where(Service.slug == slug)):
        slug, n = f"{base}-{n}", n + 1
    return slug


def save_service(db: Session, svc: Optional[Service], name: str, description: str, price: Optional[int],
                 active: bool, category_slugs: List[str]) -> Service:
    name = name.strip()
    if not 2 <= len(name) <= 120:
        raise ValueError("Enter a service name (2 to 120 characters).")
    cats = [c for c in all_categories(db) if c.slug in category_slugs]
    if not cats:
        raise ValueError("Tick at least one category.")
    if price is not None and price > 10_000_000:
        raise ValueError("That price is too large.")
    if svc is None:
        top = db.scalar(select(func.coalesce(func.max(Service.sort), 0)))
        svc = Service(slug=unique_slug(db, name), sort=top + 1)
        db.add(svc)
    svc.name, svc.description, svc.price, svc.active = name, description.strip()[:300], price, active
    svc.categories = cats
    return svc
