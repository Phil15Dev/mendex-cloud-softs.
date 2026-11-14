import csv
import io

from sqlalchemy import select

from app.modules.admin.models import AdminAuditLog
from app.modules.notifications.models import Notification
from app.modules.requests.models import RequestStatusHistory, ServiceRequest
from app.modules.services.models import Service
from tests.conftest import ADMIN_PW, make_request, post


def audit_actions(db):
    return [a.action for a in db.scalars(select(AdminAuditLog).order_by(AdminAuditLog.id))]


# ---------- requests ----------
def test_status_update_writes_history_audit_and_shows_to_customer(admin, client, db, req):
    r = post(admin, f"/admin/requests/{req.id}/status", {"status": "in_progress", "message": "We have started."})
    assert r.status_code == 303
    db.expire_all()
    got = db.get(ServiceRequest, req.id)
    assert got.status == "in_progress" and got.note == "We have started."
    assert [h.to_status for h in got.history] == ["received", "in_progress"] and got.history[-1].actor == "Owner"
    assert "request.updated" in audit_actions(db)
    from tests.conftest import new_client
    public = new_client().get(f"/track/{req.code}").text
    assert "We have started." in public and "In progress" in public


def test_unchanged_save_adds_no_history(admin, db, req):
    post(admin, f"/admin/requests/{req.id}/status", {"status": "received", "message": ""})
    db.expire_all()
    assert len(db.get(ServiceRequest, req.id).history) == 1


def test_request_list_filters_search_and_pagination(admin, db):
    for i in range(23):
        make_request(db, name=f"Customer {i}", phone=f"07120000{i:02d}", slug="tsc" if i % 2 else "kra-itax")
    assert admin.get("/admin/requests").text.count('href="/admin/requests/') >= 20
    assert admin.get("/admin/requests?page=2").status_code == 200 and admin.get("/admin/requests?page=99").status_code == 200
    only_tsc = admin.get("/admin/requests?service_id=" + str(db.scalar(select(Service.id).where(Service.slug == "tsc")))).text
    assert "KRA" not in only_tsc.split("<tbody>")[1]
    assert admin.get("/admin/requests?q=Customer 7").text.count('href="/admin/requests/') == 1
    assert "No requests found" in admin.get("/admin/requests?q=zzzznothing").text
    assert admin.get("/admin/requests?status=completed").status_code == 200
    assert admin.get("/admin/requests?q=' OR 1=1 --").status_code == 200  # SQL injection attempt is just text


def test_request_detail_404(admin):
    assert admin.get("/admin/requests/99999").status_code == 404


def test_customer_names_are_escaped(admin, db):
    r = make_request(db, name="<script>alert(1)</script>")
    html = admin.get(f"/admin/requests/{r.id}").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_new_request_notification_and_mark_read(admin, db, req):
    assert "New activity" in admin.get("/admin").text
    post(admin, "/admin/notifications/read")
    db.expire_all()
    assert db.scalar(select(Notification)).read_at is not None and "New activity" not in admin.get("/admin").text


def test_price_change_does_not_touch_old_requests(admin, db):
    old = make_request(db, slug="kuccps")  # 800
    sid = db.scalar(select(Service.id).where(Service.slug == "kuccps"))
    r = post(admin, f"/admin/services/{sid}", {"name": "KUCCPS", "description": "x", "price": "900", "active": "on", "category": ["government"]})
    assert r.status_code == 303
    new = make_request(db, slug="kuccps", phone="0700000001")
    db.expire_all()
    assert db.get(ServiceRequest, old.id).fee == 800 and db.get(ServiceRequest, new.id).fee == 900
    assert any("price=900" in (a.detail or "") for a in db.scalars(select(AdminAuditLog)))


def test_requests_can_be_searched_by_code_name_and_phone(admin, db):
    a, b = make_request(db, name="Amina Hassan"), make_request(db, name="Brian Otieno", phone="0700000002")
    html = admin.get("/admin/requests?q=Amina").text
    assert a.code in html and b.code not in html
    assert b.code in admin.get("/admin/requests?q=0700000002").text
    assert a.code in admin.get(f"/admin/requests?q={a.code}").text


def test_payments_are_gone_from_the_admin(admin):
    for url in ("/admin/payments", "/admin/export/payments.csv"):
        assert admin.get(url).status_code in (404, 405), url


# ---------- services ----------
def test_add_edit_hide_service(admin, client, db):
    r = post(admin, "/admin/services", {"name": "KCSE results slip", "description": "Get your slip", "price": "300", "category": ["education", "online"], "active": "on"})
    assert r.status_code == 303
    svc = db.scalar(select(Service).where(Service.slug == "kcse-results-slip"))
    assert svc.price == 300 and svc.category_slugs == ["education", "online"]
    assert "KCSE results slip" in client.get("/").text and any(s["slug"] == "kcse-results-slip" for s in client.get("/api/services").json())
    post(admin, "/admin/services", {"name": "KCSE results slip", "category": ["online"], "active": "on"})
    assert db.scalar(select(Service).where(Service.slug == "kcse-results-slip-2")).price is None  # unique slug, ask for quote
    post(admin, f"/admin/services/{svc.id}", {"name": "KCSE results slip", "description": "", "price": "", "category": ["online"]})  # no 'active' = hidden
    db.expire_all()
    assert db.get(Service, svc.id).active is False and all(s["slug"] != "kcse-results-slip" for s in client.get("/api/services").json())


def test_service_validation(admin, db):
    before = len(db.scalars(select(Service)).all())
    post(admin, "/admin/services", {"name": "x", "category": ["online"]})
    post(admin, "/admin/services", {"name": "No category"})
    assert len(db.scalars(select(Service)).all()) == before


def test_seed_never_overwrites_admin_edits(admin, db):
    from app.main import startup_seed
    sid = db.scalar(select(Service.id).where(Service.slug == "tsc"))
    post(admin, f"/admin/services/{sid}", {"name": "TSC renamed", "description": "d", "price": "999", "category": ["online"], "active": "on"})
    startup_seed(); db.expire_all()
    assert db.get(Service, sid).name == "TSC renamed" and db.get(Service, sid).price == 999


# ---------- customers, dashboard, reports, exports ----------
def test_customers_pages(admin, db):
    make_request(db, name="Amina Hassan"); make_request(db, name="Amina Hassan", slug="tsc")
    html = admin.get("/admin/customers").text
    assert "Amina Hassan" in html and ">2<" in html.replace(" ", "").replace("\n", "")
    cid = db.scalar(select(__import__("app.modules.customers.models", fromlist=["Customer"]).Customer.id))
    assert admin.get(f"/admin/customers/{cid}").status_code == 200 and admin.get("/admin/customers/999").status_code == 404
    assert "Amina" in admin.get("/admin/customers?q=0712").text or "Amina" in admin.get("/admin/customers?q=Amina").text


def test_dashboard_and_report_numbers(admin, db):
    from app.modules.reports import service as reports
    a, b, c = make_request(db), make_request(db, phone="0700000002", slug="ntsa"), make_request(db, phone="0700000003", slug="tsc")
    post(admin, f"/admin/requests/{b.id}/status", {"status": "in_progress", "message": ""})
    d = reports.dashboard(db)
    assert d["new_today"] == 3 and d["awaiting"] == 2 and d["in_progress"] == 1
    assert d["chart"][-1][1] == 3 and d["top"] and admin.get("/admin").status_code == 200
    rep = reports.report(db, None, None)
    assert rep["requests"] == 3 and admin.get("/admin/reports?date_from=2026-01-01&date_to=2026-12-31").status_code == 200


def test_csv_exports(admin, db):
    make_request(db, name="=HYPERLINK(\"x\")", details="+cmd")
    make_request(db, phone="0700000002")
    resp = admin.get("/admin/export/requests.csv")
    assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/csv") and resp.text.startswith("\ufeff")
    rows = list(csv.reader(io.StringIO(resp.text.lstrip("\ufeff"))))
    assert rows[0][:5] == ["Code", "Received (EAT)", "Customer", "Phone", "Service"] and len(rows) == 3
    assert any(row[2].startswith("'=") and row[8].startswith("'+") for row in rows[1:])
    assert "Name" in admin.get("/admin/export/customers.csv").text
    assert admin.get("/admin/export/requests.csv?q=0700000002").text.count("MM-") == 1
    assert audit_actions(db).count("export.csv") >= 3
