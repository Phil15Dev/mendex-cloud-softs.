from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.constants import STATUS_LABELS
from app.core.csv import csv_response, safe
from app.core.database import get_db
from app.core.templating import eat, render
from app.core.utils import to_int, utcnow
from app.modules.admin.audit import log_action
from app.modules.auth.dependencies import AdminContext, require_perm, require_perm_post
from app.modules.customers.router import customers_stmt
from app.modules.notifications.models import Notification
from app.modules.requests.service import filter_requests

from . import service

router = APIRouter(prefix="/admin")


@router.get("")
def dashboard(request: Request, ctx: AdminContext = Depends(require_perm("reports.view")), db: Session = Depends(get_db)):
    return render(request, "admin/dashboard.html", {"d": service.dashboard(db), "nav_active": "dashboard"})


@router.post("/notifications/read")
def mark_read(request: Request, ctx: AdminContext = Depends(require_perm_post("reports.view")), db: Session = Depends(get_db)):
    db.execute(update(Notification).where(Notification.read_at.is_(None)).values(read_at=utcnow()))
    db.commit()
    return RedirectResponse("/admin", status_code=303)


@router.get("/reports")
def reports(request: Request, date_from: Optional[str] = None, date_to: Optional[str] = None,
            ctx: AdminContext = Depends(require_perm("reports.view")), db: Session = Depends(get_db)):
    return render(request, "admin/reports.html", {"r": service.report(db, date_from, date_to), "date_from": date_from or "",
                                                  "date_to": date_to or "", "nav_active": "reports"})


def _audit_export(db, request, ctx, what, n, detail=""):
    log_action(db, request, "export.csv", ctx.account, "export", what, f"{n} rows. {detail}".strip())
    db.commit()


@router.get("/export/requests.csv")
def export_requests(request: Request, status: Optional[str] = None, service_id: Optional[str] = None, q: Optional[str] = None,
                    date_from: Optional[str] = None, date_to: Optional[str] = None,
                    ctx: AdminContext = Depends(require_perm("reports.export")), db: Session = Depends(get_db)):
    rows = db.scalars(filter_requests(status, to_int(service_id or ""), q, date_from, date_to).limit(20000)).all()
    _audit_export(db, request, ctx, "requests", len(rows), str(request.url.query)[:200])
    return csv_response("requests", ["Code", "Received (EAT)", "Customer", "Phone", "Service", "Fee (KSh)", "Status",
                                     "Message to customer", "Details"],
                        [[r.code, eat(r.created_at, "%Y-%m-%d %H:%M"), safe(r.customer.name), r.customer.phone, safe(r.service_name),
                          "" if r.fee is None else r.fee, STATUS_LABELS[r.status], safe(r.note), safe(r.details)] for r in rows])


@router.get("/export/customers.csv")
def export_customers(request: Request, q: Optional[str] = None, ctx: AdminContext = Depends(require_perm("reports.export")),
                     db: Session = Depends(get_db)):
    rows = db.execute(customers_stmt(q).limit(20000)).all()
    _audit_export(db, request, ctx, "customers", len(rows))
    return csv_response("customers", ["Name", "Phone", "Requests", "Last request (EAT)"],
                        [[safe(c.name), c.phone, n, eat(last, "%Y-%m-%d %H:%M")] for c, n, last in rows])
