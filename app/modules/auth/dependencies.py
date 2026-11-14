import hmac
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import NeedLogin, PermissionDenied
from app.core.security import csrf_token_for, verify_password
from app.modules.admin.audit import log_action

from . import limits, service
from .models import AdminAccount, AdminSession


@dataclass
class AdminContext:
    account: AdminAccount
    session: AdminSession
    perms: set
    csrf_token: str


def admin_context(request: Request, db: Session = Depends(get_db)) -> AdminContext:
    token = request.cookies.get(service.COOKIE)
    found = service.resolve_session(db, token) if token else None
    if not found:
        raise NeedLogin()
    account, sess = found
    ctx = AdminContext(account, sess, {p.code for p in account.role.permissions}, csrf_token_for(token))
    request.state.admin_ctx = ctx
    return ctx


def require_perm(code: str):
    """For pages (GET): the admin must hold this permission."""
    def dep(ctx: AdminContext = Depends(admin_context)) -> AdminContext:
        if code not in ctx.perms:
            raise PermissionDenied()
        return ctx
    return dep


def require_perm_post(code: str = None):
    """For forms (POST): permission check plus a valid CSRF token."""
    async def dep(request: Request, ctx: AdminContext = Depends(admin_context)) -> AdminContext:
        if code and code not in ctx.perms:
            raise PermissionDenied()
        sent = (await request.form()).get("csrf_token", "")
        if not isinstance(sent, str) or not hmac.compare_digest(sent, ctx.csrf_token):
            raise PermissionDenied("Your form expired. Reload the page and try again.")
        return ctx
    return dep


def reauthenticate(db: Session, request: Request, ctx: AdminContext, password: str) -> bool:
    """Ask for the admin's own password again before sensitive actions."""
    key = str(ctx.account.id)
    if limits.reauth.blocked(key):
        return False
    if verify_password(ctx.account.password_hash, password or ""):
        limits.reauth.reset(key)
        return True
    limits.reauth.fail(key)
    log_action(db, request, "auth.reauth_failed", ctx.account)
    db.commit()
    return False
