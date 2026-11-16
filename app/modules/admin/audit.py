from fastapi import Request
from sqlalchemy.orm import Session

from app.core.utils import client_ip

from .models import AdminAuditLog


def log_action(db: Session, request: Request, action: str, account=None, target_type: str = "",
               target_id="", detail: str = "", actor: str = "") -> None:
    """Add an audit row to the current transaction (the caller commits)."""
    db.add(AdminAuditLog(
        admin_id=account.id if account else None,
        actor=(account.display_name if account else actor)[:80],
        action=action, target_type=target_type, target_id=str(target_id)[:40], detail=detail[:1000],
        ip=client_ip(request)[:45]))
