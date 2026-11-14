from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.constants import STATUS_LABELS
from app.core.database import get_db
from app.core.flash import flash
from app.core.templating import render
from app.core.utils import paginate, to_int
from app.modules.admin.audit import log_action
from app.modules.auth.dependencies import AdminContext, require_perm, require_perm_post
from app.modules.services.models import Service

from . import service
from .models import ServiceRequest

router = APIRouter(prefix="/admin/requests")


def read_filters(status, service_id, q, date_from, date_to) -> dict:
    return {k: v for k, v in dict(status=status, service_id=service_id, q=(q or "").strip(),
                                  date_from=date_from, date_to=date_to).items() if v}


@router.get("")
def list_requests(request: Request, status: Optional[str] = None, service_id: Optional[str] = None,
                  q: Optional[str] = None, date_from: Optional[str] = None,
                  date_to: Optional[str] = None, page: int = 1,
                  ctx: AdminContext = Depends(require_perm("requests.view")), db: Session = Depends(get_db)):
    filters = read_filters(status, service_id, q, date_from, date_to)
    stmt = service.filter_requests(status, to_int(service_id or ""), q, date_from, date_to)
    pg = paginate(db, stmt, page, 20)
    counts = dict(db.execute(select(ServiceRequest.status, func.count()).group_by(ServiceRequest.status)).all())
    return render(request, "admin/requests.html", {
        "pg": pg, "f": filters, "base_qs": urlencode(filters), "counts": counts, "total": sum(counts.values()),
        "services": db.scalars(select(Service).order_by(Service.sort)).all(), "nav_active": "requests"})


@router.get("/{rid}")
def request_detail(request: Request, rid: int, ctx: AdminContext = Depends(require_perm("requests.view")),
                   db: Session = Depends(get_db)):
    req = db.get(ServiceRequest, rid)
    if not req:
        raise HTTPException(404)
    return render(request, "admin/request_detail.html", {"r": req, "nav_active": "requests"})


@router.post("/{rid}/status")
def update_status(request: Request, rid: int, status: str = Form(""), message: str = Form(""),
                  ctx: AdminContext = Depends(require_perm_post("requests.update")), db: Session = Depends(get_db)):
    req = db.get(ServiceRequest, rid)
    if not req:
        raise HTTPException(404)
    old = req.status
    try:
        changed = service.change_status(db, req, status, message, ctx.account.display_name, ctx.account.id)
    except ValueError as e:
        flash(request, "error", str(e))
        return RedirectResponse(f"/admin/requests/{rid}", status_code=303)
    if changed:
        log_action(db, request, "request.updated", ctx.account, "request", req.code,
                   f"{STATUS_LABELS[old]} -> {STATUS_LABELS[status]}" + (f" | message: {req.note[:120]}" if req.note else ""))
        db.commit()
        flash(request, "ok", f"Saved {req.code}.")
    else:
        flash(request, "ok", "Nothing changed.")
    return RedirectResponse(f"/admin/requests/{rid}", status_code=303)
