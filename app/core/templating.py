import os
from datetime import timedelta, timezone
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from .config import settings
from .constants import STATUS_LABELS, STATUS_STYLES
from .flash import pop_flash

EAT = timezone(timedelta(hours=3))  # Kenya time, no daylight saving


def eat(dt, fmt="%d %b %Y, %H:%M"):
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(EAT).strftime(fmt)


def phone_display(number: str) -> str:
    """254708337199 -> 0708 337 199 (how Kenyans write it)."""
    local = "0" + number[3:] if number.startswith("254") else number
    return f"{local[:4]} {local[4:7]} {local[7:]}".strip()


templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent.parent / "templates"))
templates.env.globals.update(
    biz=settings.business_name, wa_number=settings.whatsapp_number, channel_url=settings.whatsapp_channel_url,
    contact_email=settings.contact_email, base_url=settings.public_base_url.rstrip('/'), on_vercel=bool(os.environ.get('VERCEL')), phone_display=phone_display(settings.whatsapp_number), STATUS_LABELS=STATUS_LABELS, STATUS_STYLES=STATUS_STYLES,
)
templates.env.filters["eat"] = eat
templates.env.filters["money"] = lambda p: "Ask for quote" if p is None else f"KSh {p:,}"
templates.env.filters["kes"] = lambda n: f"KSh {int(n or 0):,}"


def render(request: Request, name: str, ctx: dict = None, status: int = 200):
    """Render a template; inside the admin area it also receives the admin, permissions and CSRF token."""
    ctx = dict(ctx or {})
    actx = getattr(request.state, "admin_ctx", None)
    if actx:
        ctx.update(admin=actx.account, perms=actx.perms, csrf_token=actx.csrf_token)
    ctx.setdefault("flash", pop_flash(request))
    return templates.TemplateResponse(request, name, ctx, status_code=status)
