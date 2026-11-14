from typing import Optional

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (IDLE_TIMEOUT, RESET_TTL, SESSION_MAX, aware, hash_password, new_token, sha256_hex)
from app.core.utils import utcnow
from app.modules.admin.models import AdminRole
from app.modules.admin.rbac import seed_rbac

from .models import AdminAccount, AdminSession, PasswordReset

COOKIE = "admin_session"


def bootstrap_admin(db: Session) -> None:
    """First start only: create roles and the owner account from ADMIN_USERNAME / ADMIN_PASSWORD."""
    seed_rbac(db)
    if db.scalar(select(AdminAccount.id).limit(1)):
        return
    owner = db.scalar(select(AdminRole).where(AdminRole.name == "owner"))
    db.add(AdminAccount(username=settings.admin_username.strip(), full_name=settings.admin_full_name,
                        email=(settings.admin_email or settings.contact_email).strip().lower(),
                        password_hash=hash_password(settings.admin_password), role_id=owner.id))
    db.commit()


def find_login_account(db: Session, identifier: str) -> Optional[AdminAccount]:
    """Sign-in accepts a username or an email address. A username match wins; an email only
    counts when exactly one account uses it, so two admins sharing an address can't be mixed up."""
    account = find_account(db, identifier)
    if account or "@" not in identifier:
        return account
    matches = db.scalars(select(AdminAccount).where(func.lower(AdminAccount.email) == identifier.strip().lower()).limit(2)).all()
    return matches[0] if len(matches) == 1 else None


def find_account(db: Session, username: str) -> Optional[AdminAccount]:
    return db.scalar(select(AdminAccount).where(func.lower(AdminAccount.username) == username.strip().lower()))


def start_session(db: Session, account: AdminAccount, request: Request) -> str:
    token, now = new_token(), utcnow()
    db.add(AdminSession(account_id=account.id, token_hash=sha256_hex(token), created_at=now, last_seen_at=now,
                        expires_at=now + SESSION_MAX, ip=(request.client.host if request.client else "")[:45],
                        user_agent=request.headers.get("user-agent", "")[:200]))
    account.last_login_at = now
    return token


def resolve_session(db: Session, token: str):
    """Return (account, session) for a valid cookie token, else None."""
    sess = db.scalar(select(AdminSession).where(AdminSession.token_hash == sha256_hex(token)))
    now = utcnow()
    if (not sess or sess.revoked_at is not None or aware(sess.expires_at) <= now
            or now - aware(sess.last_seen_at) > IDLE_TIMEOUT):
        if sess and sess.revoked_at is None:
            sess.revoked_at = now
            db.commit()
        return None
    account = db.get(AdminAccount, sess.account_id)
    if not account or not account.active:
        return None
    if (now - aware(sess.last_seen_at)).total_seconds() > 60:  # touch at most once a minute
        sess.last_seen_at = now
        db.commit()
    return account, sess


def revoke_session(db: Session, token: str) -> None:
    sess = db.scalar(select(AdminSession).where(AdminSession.token_hash == sha256_hex(token)))
    if sess and sess.revoked_at is None:
        sess.revoked_at = utcnow()


def revoke_all(db: Session, account_id: int) -> None:
    db.execute(update(AdminSession).where(AdminSession.account_id == account_id, AdminSession.revoked_at.is_(None))
               .values(revoked_at=utcnow()))


def create_reset(db: Session, account: AdminAccount) -> str:
    now = utcnow()
    db.execute(update(PasswordReset).where(PasswordReset.account_id == account.id, PasswordReset.used_at.is_(None))
               .values(used_at=now))
    token = new_token()
    db.add(PasswordReset(account_id=account.id, token_hash=sha256_hex(token), created_at=now, expires_at=now + RESET_TTL))
    return token


def usable_reset(db: Session, token: str):
    pr = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == sha256_hex(token)))
    return pr if pr and pr.used_at is None and aware(pr.expires_at) > utcnow() else None


def claim_reset(db: Session, pr: PasswordReset) -> bool:
    """Mark the link used. Only one of two simultaneous clicks wins."""
    return db.execute(update(PasswordReset).where(PasswordReset.id == pr.id, PasswordReset.used_at.is_(None))
                      .values(used_at=utcnow())).rowcount == 1
