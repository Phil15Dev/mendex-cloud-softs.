import re

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.flash import flash
from app.core.security import (DUMMY_HASH, hash_password, needs_rehash, password_problem, verify_password)
from app.core.templating import render
from app.core.utils import client_ip, utcnow
from app.modules.admin.audit import log_action
from app.modules.notifications.service import send_reset_email

from . import limits, service
from .dependencies import AdminContext, admin_context, reauthenticate, require_perm_post
from .models import AdminAccount

router = APIRouter(prefix="/admin")
COOKIE = service.COOKIE
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
GENERIC_ERROR = "Invalid email or password."


def ip_of(request: Request) -> str:
    return client_ip(request) or "unknown"


def set_cookie(response, token: str, secure: bool) -> None:
    from app.core.security import SESSION_MAX
    response.set_cookie(COOKIE, token, max_age=int(SESSION_MAX.total_seconds()), httponly=True,
                        secure=secure, samesite="strict", path="/admin")


@router.get("/login")
def login_page(request: Request):
    return render(request, "auth/login.html")


@router.post("/login")
def login(request: Request, username: str = Form(""), password: str = Form(""), db: Session = Depends(get_db)):
    from app.core.config import settings
    username = username.strip()
    if not username or not password:
        return render(request, "auth/login.html", {"error": "Enter your email address and password."}, 422)
    ip = ip_of(request)
    key = f"{ip}|{username.lower()[:254]}"
    if limits.login_by_user.blocked(key) or limits.login_by_ip.blocked(ip):
        mins = max(limits.login_by_user.retry_minutes(key), limits.login_by_ip.retry_minutes(ip))
        return render(request, "auth/login.html",
                      {"error": f"Too many attempts. Try again in about {mins} minute{'s' if mins != 1 else ''}."}, 429)
    account = service.find_login_account(db, username) if len(username) <= 254 and len(password) <= 200 else None
    ok = verify_password(account.password_hash if account else DUMMY_HASH, password[:200])
    if not (account and ok):
        limits.login_by_user.fail(key)
        limits.login_by_ip.fail(ip)
        log_action(db, request, "auth.login_failed", actor=username[:64], detail="wrong credentials")
        db.commit()
        return render(request, "auth/login.html", {"error": GENERIC_ERROR}, 401)  # never says which part was wrong
    if not account.active:
        log_action(db, request, "auth.login_denied", account, detail="account deactivated")
        db.commit()
        return render(request, "auth/login.html",
                      {"error": "This account has been deactivated. Contact the business owner."}, 403)
    limits.login_by_user.reset(key)
    old = request.cookies.get(COOKIE)
    if old:
        service.revoke_session(db, old)  # session fixation: an old cookie never survives a new login
    if needs_rehash(account.password_hash):
        account.password_hash = hash_password(password)
    token = service.start_session(db, account, request)
    log_action(db, request, "auth.login", account)
    db.commit()
    response = RedirectResponse("/admin", status_code=303)
    set_cookie(response, token, settings.https_only)
    return response


@router.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if token:
        found = service.resolve_session(db, token)
        service.revoke_session(db, token)
        if found:
            log_action(db, request, "auth.logout", found[0])
        db.commit()
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(COOKIE, path="/admin")
    return response


# ---------- forgot / reset ----------
@router.get("/forgot-password")
def forgot_page(request: Request):
    return render(request, "auth/forgot.html")


@router.post("/forgot-password")
def forgot(request: Request, background: BackgroundTasks, email: str = Form(""), db: Session = Depends(get_db)):
    from app.core.config import settings
    ip = ip_of(request)
    if limits.reset_by_ip.blocked(ip):
        return render(request, "auth/forgot.html", {"error": "Too many requests. Please try again later."}, 429)
    limits.reset_by_ip.fail(ip)
    email = email.strip().lower()
    if len(email) <= 254 and EMAIL_RE.match(email):
        account = db.scalar(select(AdminAccount).where(func.lower(AdminAccount.email) == email, AdminAccount.active.is_(True)))
        if account:
            token = service.create_reset(db, account)
            log_action(db, request, "auth.password_reset_requested", account)
            db.commit()
            background.add_task(send_reset_email, account.email, f"{settings.public_base_url.rstrip('/')}/admin/reset-password/{token}")
    return render(request, "auth/forgot.html", {"sent": True})  # same answer for every email


@router.get("/reset-password/{token}")
def reset_page(request: Request, token: str, db: Session = Depends(get_db)):
    if not service.usable_reset(db, token):
        return render(request, "auth/reset.html", {"invalid": True}, 400)
    return render(request, "auth/reset.html", {"token": token})


@router.post("/reset-password/{token}")
def reset(request: Request, token: str, password: str = Form(""), confirm: str = Form(""), db: Session = Depends(get_db)):
    pr = service.usable_reset(db, token)
    if not pr:
        return render(request, "auth/reset.html", {"invalid": True}, 400)
    error = password_problem(password) or (None if password == confirm else "The two passwords do not match.")
    if error:
        return render(request, "auth/reset.html", {"token": token, "error": error}, 422)
    if not service.claim_reset(db, pr):
        db.rollback()
        return render(request, "auth/reset.html", {"invalid": True}, 400)
    account = db.get(AdminAccount, pr.account_id)
    account.password_hash, account.password_changed_at = hash_password(password), utcnow()
    service.revoke_all(db, account.id)  # every existing session ends
    log_action(db, request, "auth.password_reset_done", account)
    db.commit()
    flash(request, "ok", "Password updated. Log in with your new password.")
    return RedirectResponse("/admin/login", status_code=303)


# ---------- my account ----------
@router.get("/account")
def account_page(request: Request, ctx: AdminContext = Depends(admin_context)):
    return render(request, "admin/account.html", {"nav_active": "account"})


@router.post("/account/password")
def change_password(request: Request, current_password: str = Form(""), password: str = Form(""),
                    confirm: str = Form(""), ctx: AdminContext = Depends(require_perm_post()),
                    db: Session = Depends(get_db)):
    if not reauthenticate(db, request, ctx, current_password):
        flash(request, "error", "Your current password is wrong, or there were too many tries. Wait and try again.")
        return RedirectResponse("/admin/account", status_code=303)
    error = password_problem(password) or (None if password == confirm else "The two new passwords do not match.")
    if error:
        flash(request, "error", error)
        return RedirectResponse("/admin/account", status_code=303)
    account = ctx.account
    account.password_hash, account.password_changed_at = hash_password(password), utcnow()
    service.revoke_all(db, account.id)  # a password change signs out every session, including this one
    log_action(db, request, "auth.password_changed", account)
    db.commit()
    flash(request, "ok", "Password changed. Log in again with the new password.")
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(COOKIE, path="/admin")
    return response
