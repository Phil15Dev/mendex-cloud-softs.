from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.templating import render
from app.core.utils import paginate, phone_search_terms
from app.modules.auth.dependencies import AdminContext, require_perm
from app.modules.requests.models import ServiceRequest

from .models import Customer

router = APIRouter(prefix="/admin/customers")


def customers_stmt(q: Optional[str]):
    stmt = (select(Customer, func.count(ServiceRequest.id).label("n"), func.max(ServiceRequest.created_at).label("last"))
            .outerjoin(ServiceRequest, ServiceRequest.customer_id == Customer.id).group_by(Customer.id)
            .order_by(func.max(ServiceRequest.created_at).desc().nulls_last(), Customer.id.desc()))
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Customer.name.ilike(like), Customer.phone.ilike(like), *[Customer.phone.like(f"%{t}%") for t in phone_search_terms(q)]))
    return stmt


@router.get("")
def list_customers(request: Request, q: Optional[str] = None, page: int = 1,
                   ctx: AdminContext = Depends(require_perm("customers.view")), db: Session = Depends(get_db)):
    pg = paginate(db, customers_stmt(q), page, 20, rows=True)
    return render(request, "admin/customers.html", {"pg": pg, "q": q or "", "nav_active": "customers"})


@router.get("/{cid}")
def customer_detail(request: Request, cid: int, ctx: AdminContext = Depends(require_perm("customers.view")),
                    db: Session = Depends(get_db)):
    cust = db.get(Customer, cid)
    if not cust:
        raise HTTPException(404)
    reqs = db.scalars(select(ServiceRequest).where(ServiceRequest.customer_id == cid).order_by(ServiceRequest.id.desc())).all()
    return render(request, "admin/customer_detail.html", {
        "cust": cust, "reqs": reqs, "nav_active": "customers"})
