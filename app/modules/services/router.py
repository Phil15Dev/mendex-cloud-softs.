from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.flash import flash
from app.core.templating import render
from app.core.utils import to_int
from app.modules.admin.audit import log_action
from app.modules.auth.dependencies import AdminContext, require_perm, require_perm_post

from . import service
from .models import Service

router = APIRouter(prefix="/admin/services")


@router.get("")
def list_services(request: Request, ctx: AdminContext = Depends(require_perm("services.manage")), db: Session = Depends(get_db)):
    services = db.scalars(select(Service).order_by(Service.sort, Service.id)).all()
    return render(request, "admin/services.html", {"services": services, "nav_active": "services"})


@router.get("/new")
def new_form(request: Request, ctx: AdminContext = Depends(require_perm("services.manage")), db: Session = Depends(get_db)):
    return render(request, "admin/service_form.html", {"svc": None, "categories": service.all_categories(db), "nav_active": "services"})


@router.get("/{sid}/edit")
def edit_form(request: Request, sid: int, ctx: AdminContext = Depends(require_perm("services.manage")), db: Session = Depends(get_db)):
    svc = db.get(Service, sid)
    if not svc:
        raise HTTPException(404)
    return render(request, "admin/service_form.html", {"svc": svc, "categories": service.all_categories(db), "nav_active": "services"})


def _save(request, db, ctx, svc: Optional[Service], name, description, price, active, category):
    creating = svc is None
    old = None if creating else f"{svc.name} | {svc.price} | active={svc.active}"
    try:
        svc = service.save_service(db, svc, name, description, to_int(price), active is not None, category)
    except ValueError as e:
        db.rollback()
        flash(request, "error", str(e))
        return RedirectResponse("/admin/services/new" if creating else f"/admin/services/{svc.id}/edit", status_code=303)
    db.flush()
    log_action(db, request, "service.created" if creating else "service.updated", ctx.account, "service", svc.id,
               f"{svc.name} | price={svc.price} | active={svc.active}" + (f" (was {old})" if old else ""))
    db.commit()
    flash(request, "ok", f"{'Added' if creating else 'Saved'} “{svc.name}”.")
    return RedirectResponse("/admin/services", status_code=303)


@router.post("")
def create(request: Request, name: str = Form(""), description: str = Form(""), price: str = Form(""),
           active: Optional[str] = Form("on"), category: List[str] = Form([]),
           ctx: AdminContext = Depends(require_perm_post("services.manage")), db: Session = Depends(get_db)):
    return _save(request, db, ctx, None, name, description, price, active, category)


@router.post("/{sid}")
def update(request: Request, sid: int, name: str = Form(""), description: str = Form(""), price: str = Form(""),
           active: Optional[str] = Form(None), category: List[str] = Form([]),
           ctx: AdminContext = Depends(require_perm_post("services.manage")), db: Session = Depends(get_db)):
    svc = db.get(Service, sid)
    if not svc:
        raise HTTPException(404)
    return _save(request, db, ctx, svc, name, description, price, active, category)
