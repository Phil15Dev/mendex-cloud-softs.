import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.flash import flash
from app.core.security import hash_password, password_problem
from app.core.templating import render
from app.core.utils import paginate, utcnow
from app.modules.auth import service as auth_service
from app.modules.auth.dependencies import AdminContext, reauthenticate, require_perm, require_perm_post
from app.modules.auth.models import AdminAccount

from .audit import log_action
from .models import AdminAuditLog, AdminRole

router = APIRouter(prefix="/admin")
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")


def active_owners(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AdminAccount).join(AdminRole, AdminAccount.role_id == AdminRole.id)
                     .where(AdminRole.name == "owner", AdminAccount.active.is_(True))) or 0


@router.get("/team")
def team(request: Request, ctx: AdminContext = Depends(require_perm("admins.manage")), db: Session = Depends(get_db)):
    admins = db.scalars(select(AdminAccount).order_by(AdminAccount.id)).all()
    return render(request, "admin/team.html", {"admins": admins, "nav_active": "team"})


@router.get("/team/new")
def team_new(request: Request, ctx: AdminContext = Depends(require_perm("admins.manage")), db: Session = Depends(get_db)):
    return render(request, "admin/team_form.html", {"target": None, "roles": db.scalars(select(AdminRole)).all(), "nav_active": "team"})


@router.get("/team/{aid}")
def team_edit(request: Request, aid: int, ctx: AdminContext = Depends(require_perm("admins.manage")), db: Session = Depends(get_db)):
    target = db.get(AdminAccount, aid)
    if not target:
        raise HTTPException(404)
    return render(request, "admin/team_form.html", {"target": target, "roles": db.scalars(select(AdminRole)).all(), "nav_active": "team"})


@router.post("/team")
def team_create(request: Request, username: str = Form(""), full_name: str = Form(""), email: str = Form(""),
                role_id: int = Form(0), password: str = Form(""), current_password: str = Form(""),
                ctx: AdminContext = Depends(require_perm_post("admins.manage")), db: Session = Depends(get_db)):
    back = RedirectResponse("/admin/team/new", status_code=303)
    username, email = username.strip(), email.strip().lower()
    if not reauthenticate(db, request, ctx, current_password):
        flash(request, "error", "Your password is wrong, or there were too many tries.")
        return back
    role = db.get(AdminRole, role_id)
    error = (None if USERNAME_RE.match(username) else "Username: 3 to 64 letters, numbers, dots, dashes or underscores.") \
        or (None if not email or EMAIL_RE.match(email) else "Enter a valid email address.") \
        or (None if role else "Choose a role.") or password_problem(password) \
        or ("That username is taken." if auth_service.find_account(db, username) else None)
    if error:
        flash(request, "error", error)
        return back
    acct = AdminAccount(username=username, full_name=full_name.strip()[:100], email=email,
                        password_hash=hash_password(password), role_id=role.id, password_changed_at=utcnow())
    db.add(acct)
    db.flush()
    log_action(db, request, "admin.created", ctx.account, "admin", acct.id, f"{username} as {role.name}")
    db.commit()
    flash(request, "ok", f"Created {username}. Give them the temporary password in person.")
    return RedirectResponse("/admin/team", status_code=303)


@router.post("/team/{aid}")
def team_update(request: Request, aid: int, full_name: str = Form(""), email: str = Form(""), role_id: int = Form(0),
                active: Optional[str] = Form(None), password: str = Form(""), current_password: str = Form(""),
                ctx: AdminContext = Depends(require_perm_post("admins.manage")), db: Session = Depends(get_db)):
    target = db.get(AdminAccount, aid)
    if not target:
        raise HTTPException(404)
    back = RedirectResponse(f"/admin/team/{aid}", status_code=303)
    if not reauthenticate(db, request, ctx, current_password):
        flash(request, "error", "Your password is wrong, or there were too many tries. Nothing was changed.")
        return back
    role, email, want_active = db.get(AdminRole, role_id), email.strip().lower(), active is not None
    error = (None if role else "Choose a role.") or (None if not email or EMAIL_RE.match(email) else "Enter a valid email address.") \
        or (password_problem(password) if password else None)
    was_owner = target.role.name == "owner" and target.active
    if not error and was_owner and (role.name != "owner" or not want_active) and active_owners(db) <= 1:
        error = "There must always be one active owner."
    if not error and target.id == ctx.account.id and not want_active:
        error = "You cannot deactivate your own account."
    if error:
        flash(request, "error", error)
        return back
    role_changed, active_changed = role.id != target.role_id, want_active != target.active
    changes = []
    if role_changed:
        changes.append(f"role {target.role.name} -> {role.name}")
    if active_changed:
        changes.append("activated" if want_active else "deactivated")
    if password:
        changes.append("password reset")
    target.full_name, target.email, target.role_id, target.active = full_name.strip()[:100], email, role.id, want_active
    if password:
        target.password_hash, target.password_changed_at = hash_password(password), utcnow()
    if password or role_changed or not want_active:
        auth_service.revoke_all(db, target.id)  # permissions or access changed: end their sessions now
    log_action(db, request, "admin.updated", ctx.account, "admin", target.id, f"{target.username}: " + (", ".join(changes) or "details"))
    db.commit()
    flash(request, "ok", f"Saved {target.username}.")
    return RedirectResponse("/admin/team", status_code=303)


@router.get("/audit")
def audit(request: Request, action: Optional[str] = None, q: Optional[str] = None, page: int = 1,
          ctx: AdminContext = Depends(require_perm("audit.view")), db: Session = Depends(get_db)):
    stmt = select(AdminAuditLog).order_by(AdminAuditLog.id.desc())
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(AdminAuditLog.detail.ilike(like) | AdminAuditLog.actor.ilike(like) | AdminAuditLog.target_id.ilike(like))
    actions = [a for (a,) in db.execute(select(AdminAuditLog.action).distinct().order_by(AdminAuditLog.action))]
    f = {k: v for k, v in dict(action=action, q=(q or "").strip()).items() if v}
    from urllib.parse import urlencode
    return render(request, "admin/audit.html", {"pg": paginate(db, stmt, page, 30), "actions": actions, "f": f,
                                                "base_qs": urlencode(f), "nav_active": "audit"})
