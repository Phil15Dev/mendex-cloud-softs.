"""Recovery tool for the admin account.

    python -m app.cli reset-password [username]

Sets a new password (asks twice, nothing is shown on screen), re-activates the account and signs out every session.
Use it if you are locked out and email reset is not set up.
"""
import getpass
import sys

from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password, password_problem
from app.core.utils import utcnow
from app.modules.admin.models import AdminAuditLog, AdminRole
from app.modules.auth import service
from app.modules.auth.models import AdminAccount


def reset_password(username: str = None, password: str = None) -> int:
    with SessionLocal() as db:
        if username:
            account = service.find_account(db, username)
        else:
            account = db.scalar(select(AdminAccount).join(AdminRole, AdminAccount.role_id == AdminRole.id)
                                .where(AdminRole.name == "owner").order_by(AdminAccount.id))
        if not account:
            print("No such administrator. Start the app once so the first account is created, then try again.")
            return 1
        if password is None:
            password = getpass.getpass(f"New password for '{account.username}': ")
            if password != getpass.getpass("Repeat the password: "):
                print("The passwords do not match.")
                return 1
        problem = password_problem(password)
        if problem:
            print(problem)
            return 1
        account.password_hash, account.password_changed_at, account.active = hash_password(password), utcnow(), True
        service.revoke_all(db, account.id)
        db.add(AdminAuditLog(admin_id=account.id, actor=account.display_name, action="auth.password_reset_cli",
                             detail="reset from the command line"))
        db.commit()
    print("Password updated. All sessions were signed out.")
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "reset-password":
        return reset_password(argv[1] if len(argv) > 1 else None)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
