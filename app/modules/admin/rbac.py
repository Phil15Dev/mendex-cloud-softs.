from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import PERMISSIONS, ROLE_DEFAULTS

from .models import AdminRole, Permission


def seed_rbac(db: Session) -> None:
    """Create missing permissions and roles. Existing roles are never overwritten."""
    perms = {p.code: p for p in db.scalars(select(Permission))}
    for code, desc in PERMISSIONS.items():
        if code not in perms:
            perms[code] = Permission(code=code, description=desc)
            db.add(perms[code])
    db.flush()
    existing = {r.name for r in db.scalars(select(AdminRole))}
    for name, (desc, codes) in ROLE_DEFAULTS.items():
        if name not in existing:
            db.add(AdminRole(name=name, description=desc, permissions=[perms[c] for c in codes]))
    db.commit()
