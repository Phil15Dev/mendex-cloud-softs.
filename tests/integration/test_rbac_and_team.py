from sqlalchemy import select

from app.modules.admin.models import AdminAuditLog
from app.modules.auth.models import AdminAccount, AdminSession
from tests.conftest import ADMIN_PW, csrf, login, logged_in, make_request, new_client, post


def test_staff_can_work_requests_but_not_settings_or_team(db):
    r = make_request(db)
    staff = logged_in(db, "sam", "staff")
    assert staff.get("/admin").status_code == 200 and staff.get(f"/admin/requests/{r.id}").status_code == 200
    assert post(staff, f"/admin/requests/{r.id}/status", {"status": "in_progress", "message": "ok"}).status_code == 303
    for url in ("/admin/services", "/admin/team", "/admin/audit", "/admin/export/requests.csv", "/admin/export/customers.csv"):
        assert staff.get(url).status_code == 403, url
    assert post(staff, "/admin/services", {"name": "Hack", "category": ["online"]}).status_code == 403
    assert "Team" not in staff.get("/admin").text.split("</nav>")[0]


def test_manager_runs_operations_but_not_the_team(db):
    r = make_request(db)
    mgr = logged_in(db, "mia", "manager")
    assert post(mgr, f"/admin/requests/{r.id}/status", {"status": "in_progress", "message": "ok"}).status_code == 303
    assert mgr.get("/admin/services").status_code == 200 and mgr.get("/admin/export/requests.csv").status_code == 200
    assert mgr.get("/admin/team").status_code == 403 and mgr.get("/admin/audit").status_code == 403


def test_owner_creates_admin_with_reauth(admin, db):
    base = {"username": "newbie", "full_name": "New Bie", "email": "n@example.com", "role_id": 3, "password": "Temp-Password-1"}
    from app.modules.admin.models import AdminRole
    base["role_id"] = db.scalar(select(AdminRole.id).where(AdminRole.name == "staff"))
    post(admin, "/admin/team", {**base, "current_password": "wrong"})
    assert db.scalar(select(AdminAccount).where(AdminAccount.username == "newbie")) is None
    post(admin, "/admin/team", {**base, "password": "short", "current_password": ADMIN_PW})
    assert db.scalar(select(AdminAccount).where(AdminAccount.username == "newbie")) is None
    assert post(admin, "/admin/team", {**base, "current_password": ADMIN_PW}).status_code == 303
    assert db.scalar(select(AdminAccount).where(AdminAccount.username == "newbie")).password_hash.startswith("$argon2id$")
    post(admin, "/admin/team", {**base, "current_password": ADMIN_PW})  # duplicate username
    assert len(db.scalars(select(AdminAccount).where(AdminAccount.username == "newbie")).all()) == 1
    assert login(new_client(), "newbie", "Temp-Password-1").status_code == 303


def test_deactivating_or_changing_role_signs_the_person_out(admin, db):
    staff = logged_in(db, "sam", "staff")
    assert staff.get("/admin/requests").status_code == 200
    sam = db.scalar(select(AdminAccount).where(AdminAccount.username == "sam"))
    from app.modules.admin.models import AdminRole
    mgr = db.scalar(select(AdminRole.id).where(AdminRole.name == "manager"))
    post(admin, f"/admin/team/{sam.id}", {"full_name": "Sam", "email": "", "role_id": mgr, "active": "on", "current_password": ADMIN_PW})
    assert staff.get("/admin/requests").status_code == 303  # role changed: session ended
    again = new_client(); login(again, "sam", "Staff-Pass-12345")
    assert again.get("/admin/services").status_code == 200
    post(admin, f"/admin/team/{sam.id}", {"full_name": "Sam", "email": "", "role_id": mgr, "current_password": ADMIN_PW})  # no 'active' = deactivate
    assert again.get("/admin", ).status_code == 303 and login(new_client(), "sam", "Staff-Pass-12345").status_code == 403


def test_last_owner_and_self_deactivation_are_protected(admin, db):
    from app.modules.admin.models import AdminRole
    owner = db.scalar(select(AdminAccount).where(AdminAccount.username == "admin"))
    staff_role = db.scalar(select(AdminRole.id).where(AdminRole.name == "staff"))
    post(admin, f"/admin/team/{owner.id}", {"full_name": "Owner", "email": "", "role_id": staff_role, "active": "on", "current_password": ADMIN_PW})
    post(admin, f"/admin/team/{owner.id}", {"full_name": "Owner", "email": "", "role_id": owner.role_id, "current_password": ADMIN_PW})
    db.expire_all()
    o = db.get(AdminAccount, owner.id)
    assert o.active and o.role.name == "owner"


def test_team_changes_are_audited(admin, db):
    from app.modules.admin.models import AdminRole
    post(admin, "/admin/team", {"username": "audited", "role_id": db.scalar(select(AdminRole.id).where(AdminRole.name == "staff")),
                                "password": "Temp-Password-1", "current_password": ADMIN_PW})
    assert "admin.created" in [a.action for a in db.scalars(select(AdminAuditLog))] and "audited" in admin.get("/admin/audit").text
    assert admin.get("/admin/audit?action=admin.created").status_code == 200 and admin.get("/admin/audit?q=audited").status_code == 200


def test_changing_own_password_signs_out_every_session(admin, db):
    other = new_client(); login(other)
    assert other.get("/admin").status_code == 200
    post(admin, "/admin/account/password", {"current_password": "wrong", "password": "Brand-New-Pass-99", "confirm": "Brand-New-Pass-99"})
    assert login(new_client(), password="Brand-New-Pass-99").status_code == 401
    post(admin, "/admin/account/password", {"current_password": ADMIN_PW, "password": "Brand-New-Pass-99", "confirm": "Brand-New-Pass-99"})
    assert other.get("/admin").status_code == 303 and admin.get("/admin").status_code == 303
    assert login(new_client(), password=ADMIN_PW).status_code == 401 and login(new_client(), password="Brand-New-Pass-99").status_code == 303
