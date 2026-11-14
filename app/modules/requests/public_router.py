from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.templating import render
from app.modules.notifications.models import Notification
from app.modules.notifications.service import send_mail
from app.modules.services import service as services

from . import service
from .models import ServiceRequest

router = APIRouter()
HERO_PHOTO = Path(__file__).resolve().parents[2] / "static" / "hero.jpg"  # optional: drop your own photo here


def render_index(request: Request, db: Session, selected=None, error=None, form=None, status=200):
    items = services.active_services(db)
    groups = {c.slug: [s for s in items if c.slug in s.category_slugs] for c in services.all_categories(db)}
    return render(request, "public/index.html", {
        "services": items, "groups": groups, "selected": selected, "error": error, "form": form or {},
        "has_hero": HERO_PHOTO.exists()}, status)


@router.get("/")
def index(request: Request, service: Optional[str] = None, db: Session = Depends(get_db)):
    return render_index(request, db, selected=service)


@router.post("/request")
def submit_request(request: Request, background: BackgroundTasks, service_slug: str = Form("", alias="service"),
                   name: str = Form(""), phone: str = Form(""), details: str = Form(""), website: str = Form(""),
                   db: Session = Depends(get_db)):
    if website:  # honeypot: real visitors never fill this hidden field
        return RedirectResponse("/", status_code=303)
    try:
        req = service.create_request(db, service_slug, name, phone, details)
    except ValueError as e:
        return render_index(request, db, selected=service_slug, error=str(e), status=422,
                            form={"name": name, "phone": phone, "details": details})
    if settings.notify_admin_email:
        background.add_task(send_mail, settings.notify_admin_email, f"New request {req.code}",
                            f"{req.service_name} from {req.customer.name} ({req.customer.phone}).", "new_request")
    return RedirectResponse(f"/track/{req.code}?new=1", status_code=303)


@router.get("/services")
def services_page(request: Request, db: Session = Depends(get_db)):
    items = services.active_services(db)
    groups = {c.slug: [s for s in items if c.slug in s.category_slugs] for c in services.all_categories(db)}
    return render(request, "public/services.html", {"services": items, "groups": groups})


@router.get("/about")
def about(request: Request, db: Session = Depends(get_db)):
    return render(request, "public/about.html", {"services": services.active_services(db)})


def _contact_page(request, error=None, form=None, sent=False, status=200):
    return render(request, "public/contact.html", {"error": error, "form": form or {}, "sent": sent}, status)


@router.get("/contact")
def contact(request: Request, sent: bool = False):
    return _contact_page(request, sent=sent)


@router.post("/contact")
def contact_submit(request: Request, background: BackgroundTasks, name: str = Form(""), contact: str = Form(""),
                   message: str = Form(""), website: str = Form(""), db: Session = Depends(get_db)):
    if website:  # honeypot
        return RedirectResponse("/contact?sent=1", status_code=303)
    name, contact, message = name.strip(), contact.strip(), message.strip()
    form = {"name": name, "contact": contact, "message": message}
    if len(name) < 2 or len(name) > 100:
        return _contact_page(request, "Enter your name.", form, status=422)
    if not contact or len(contact) > 254:
        return _contact_page(request, "Enter a phone number or email so we can reply.", form, status=422)
    if len(message) < 5 or len(message) > 1000:
        return _contact_page(request, "Write a short message (5 to 1000 characters).", form, status=422)
    preview = f"Message from {name} ({contact}): {message}"
    db.add(Notification(kind="contact", message=(preview[:297] + "...") if len(preview) > 300 else preview))
    db.commit()
    background.add_task(send_mail, settings.notify_admin_email or settings.contact_email,
                        f"Website message from {name}", f"From: {name}\nReply to: {contact}\n\n{message}", "contact")
    return RedirectResponse("/contact?sent=1", status_code=303)


@router.get("/track")
def track_search(request: Request, code: Optional[str] = None):
    if code and code.strip():
        return RedirectResponse(f"/track/{code.strip().upper()}", status_code=303)
    return render(request, "public/track.html", {"req": None, "code": None, "new": False})


@router.get("/track/{code}")
def track(request: Request, code: str, new: bool = False, db: Session = Depends(get_db)):
    req = db.scalar(select(ServiceRequest).where(ServiceRequest.code == code.upper()))
    return render(request, "public/track.html", {"req": req, "code": code.upper(), "new": new}, 200 if req else 404)


# ---------- JSON API ----------
class RequestIn(BaseModel):
    service: str
    name: str = Field(min_length=2, max_length=100)
    phone: str
    details: str = Field("", max_length=1000)


@router.get("/api/services", tags=["api"])
def api_services(db: Session = Depends(get_db)):
    return [{"slug": s.slug, "name": s.name, "description": s.description, "categories": s.category_slugs,
             "price": s.price} for s in services.active_services(db)]


@router.post("/api/requests", status_code=201, tags=["api"])
def api_create(body: RequestIn, db: Session = Depends(get_db)):
    try:
        req = service.create_request(db, body.service, body.name, body.phone, body.details)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"code": req.code, "status": req.status}


@router.get("/api/track/{code}", tags=["api"])
def api_track(code: str, db: Session = Depends(get_db)):
    req = db.scalar(select(ServiceRequest).where(ServiceRequest.code == code.upper()))
    if not req:
        raise HTTPException(404, "Request not found.")
    return {"code": req.code, "service": req.service_name, "status": req.status, "message": req.note,
            "updated_at": req.updated_at}
