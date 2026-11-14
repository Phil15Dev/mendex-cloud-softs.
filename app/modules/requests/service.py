from datetime import datetime, time, timedelta
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.constants import STATUS_LABELS
from app.core.templating import EAT
from app.core.utils import new_request_code, normalize_phone, phone_search_terms
from app.modules.customers.models import Customer
from app.modules.customers.service import upsert_customer
from app.modules.notifications.service import notify_new_request
from app.modules.services.models import Service

from .models import RequestStatusHistory, ServiceRequest


def create_request(db: Session, slug: str, name: str, phone: str, details: str) -> ServiceRequest:
    svc = db.scalar(select(Service).where(Service.slug == slug, Service.active.is_(True)))
    if not svc:
        raise ValueError("Please choose a service.")
    name = name.strip()
    if len(name) < 2:
        raise ValueError("Enter your name.")
    phone = normalize_phone(phone)
    cust = upsert_customer(db, phone, name[:100])
    code = new_request_code()
    while db.scalar(select(ServiceRequest.id).where(ServiceRequest.code == code)):
        code = new_request_code()
    req = ServiceRequest(code=code, service_id=svc.id, customer_id=cust.id, service_name=svc.name, fee=svc.price,
                         details=details.strip()[:1000])
    db.add(req)
    db.flush()
    db.add(RequestStatusHistory(request_id=req.id, from_status=None, to_status="received", actor="Customer"))
    notify_new_request(db, req)
    db.commit()
    return req


def change_status(db: Session, req: ServiceRequest, status: str, message: str, actor: str, admin_id: Optional[int]) -> bool:
    if status not in STATUS_LABELS:
        raise ValueError("Unknown status.")
    message = message.strip()[:500]
    if status == req.status and message == req.note:
        return False
    db.add(RequestStatusHistory(request_id=req.id, from_status=req.status, to_status=status, message=message,
                                admin_id=admin_id, actor=actor))
    req.status, req.note = status, message
    return True


def parse_day(value: Optional[str], end: bool = False) -> Optional[datetime]:
    """YYYY-MM-DD (Kenya time) to an aware datetime; end=True gives the start of the next day."""
    try:
        d = datetime.strptime(value or "", "%Y-%m-%d")
    except ValueError:
        return None
    return datetime.combine(d.date() + timedelta(days=1 if end else 0), time.min, tzinfo=EAT)


def filter_requests(status=None, service_id=None, q=None, date_from=None, date_to=None):
    """One filter used by the requests page and the CSV export, so both always agree."""
    stmt = (select(ServiceRequest).join(Customer, ServiceRequest.customer_id == Customer.id)
            .order_by(ServiceRequest.id.desc()))
    if status in STATUS_LABELS:
        stmt = stmt.where(ServiceRequest.status == status)
    if service_id:
        stmt = stmt.where(ServiceRequest.service_id == service_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        phones = [Customer.phone.like(f"%{t}%") for t in phone_search_terms(q)]
        stmt = stmt.where(or_(ServiceRequest.code.ilike(like), Customer.phone.ilike(like), Customer.name.ilike(like), *phones))
    if (start := parse_day(date_from)):
        stmt = stmt.where(ServiceRequest.created_at >= start)
    if (end := parse_day(date_to, end=True)):
        stmt = stmt.where(ServiceRequest.created_at < end)
    return stmt
