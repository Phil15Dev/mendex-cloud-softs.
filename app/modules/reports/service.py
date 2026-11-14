from datetime import datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.templating import EAT
from app.core.utils import utcnow
from app.modules.notifications.models import Notification
from app.modules.requests.models import ServiceRequest
from app.modules.requests.service import parse_day


def dashboard(db: Session) -> dict:
    now = datetime.now(EAT)
    today = datetime.combine(now.date(), time.min, tzinfo=EAT)
    week = today - timedelta(days=today.weekday())
    counts = dict(db.execute(select(ServiceRequest.status, func.count()).group_by(ServiceRequest.status)).all())
    count = lambda *where: db.scalar(select(func.count()).select_from(ServiceRequest).where(*where)) or 0
    days = [today.date() - timedelta(days=i) for i in range(13, -1, -1)]
    created = db.scalars(select(ServiceRequest.created_at).where(ServiceRequest.created_at >= today - timedelta(days=13))).all()
    per_day = {d: 0 for d in days}
    for c in created:
        d = (c if c.tzinfo else c.replace(tzinfo=timezone.utc)).astimezone(EAT).date()
        if d in per_day:
            per_day[d] += 1
    top = db.execute(select(ServiceRequest.service_name, func.count().label("n")).where(ServiceRequest.created_at >= today - timedelta(days=30))
                     .group_by(ServiceRequest.service_name).order_by(func.count().desc()).limit(5)).all()
    return {
        "counts": counts, "new_today": count(ServiceRequest.created_at >= today),
        "awaiting": counts.get("received", 0) + counts.get("needs_documents", 0),
        "in_progress": counts.get("in_progress", 0), "completed_week": count(ServiceRequest.status == "completed", ServiceRequest.updated_at >= week),
        "attention": db.scalars(select(ServiceRequest).where(ServiceRequest.status == "received",
                                ServiceRequest.created_at < utcnow() - timedelta(hours=24)).order_by(ServiceRequest.id).limit(8)).all(),
        "chart": [(d, per_day[d]) for d in days], "chart_max": max(per_day.values()) or 1, "top": top,
        "recent": db.scalars(select(ServiceRequest).order_by(ServiceRequest.id.desc()).limit(8)).all(),
        "notifications": db.scalars(select(Notification).where(Notification.read_at.is_(None)).order_by(Notification.id.desc()).limit(6)).all(),
    }


def report(db: Session, date_from: Optional[str], date_to: Optional[str]) -> dict:
    today = datetime.now(EAT).date()
    start = parse_day(date_from) or datetime.combine(today.replace(day=1), time.min, tzinfo=EAT)
    end = parse_day(date_to, end=True) or datetime.combine(today + timedelta(days=1), time.min, tzinfo=EAT)
    by_status = db.execute(select(ServiceRequest.status, func.count()).where(ServiceRequest.created_at >= start,
                           ServiceRequest.created_at < end).group_by(ServiceRequest.status)).all()
    return {"start": start.date(), "end": (end - timedelta(days=1)).date(), "by_status": by_status,
            "requests": sum(n for _, n in by_status)}
