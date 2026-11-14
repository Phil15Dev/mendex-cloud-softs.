import re
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.core.utils import utcnow
from app.modules.admin.models import AdminAuditLog
from app.modules.auth import limits
from app.modules.auth.models import AdminAccount, AdminSession, PasswordReset
from tests.conftest import ADMIN_PW, csrf, login, make_admin, make_request, new_client, post


def actions(db):
    return [a.action for a in db.scalars(select(AdminAuditLog))]


# ---------- login ----------
def test_login_page_matches_the_design(client):
    r = client.get("/admin/login")
    assert r.status_code == 200 and all(t in r.text for t in ("Admin Login", "Forgot Password?", "Fast", "Empowering your digital world", 'autocomplete="current-password"'))


def test_wrong_username_and_password_look_identical(client, db):
    a, b = login(client, "admin", "wrong-password"), login(client, "nobody", "wrong-password")
    assert a.status_code == b.status_code == 401
    strip = lambda t: re.sub(r"\s+", " ", t)
    assert "Invalid email or password." in a.text and "Invalid email or password." in b.text
    assert strip(a.text) == strip(b.text)
    assert actions(db).count("auth.login_failed") == 2


def test_login_accepts_an_email_address(client, db):
    make_admin(db, "mary", email="Mary@Example.com", password="Mary-Pass-12345")
    r = login(client, "mary@example.com", "Mary-Pass-12345")
    assert r.status_code == 303 and r.headers["location"] == "/admin"


def test_shared_email_does_not_log_anyone_in(client, db):
    make_admin(db, "one", email="same@example.com", password="One-Pass-123456")
    make_admin(db, "two", email="same@example.com", password="Two-Pass-123456")
    assert login(client, "same@example.com", "One-Pass-123456").status_code == 401


def test_empty_fields_are_a_validation_error(client):
    assert client.post("/admin/login", data={"username": "", "password": ""}).status_code == 422


def test_login_sets_a_safe_cookie_and_stores_only_a_hash(client, db):
    r = login(client)
    cookie = r.headers["set-cookie"].lower()
    assert r.status_code == 303 and r.headers["location"] == "/admin" and "httponly" in cookie and "samesite=strict" in cookie and "path=/admin" in cookie
    token = client.cookies.get("admin_session")
    row = db.scalar(select(AdminSession))
    assert row.token_hash != token and len(row.token_hash) == 64 and "auth.login" in actions(db)


def test_secure_flag_follows_https_only(client, monkeypatch):
    from app.core import config
    monkeypatch.setattr(config.settings, "https_only", True)
    assert "secure" in login(client).headers["set-cookie"].lower()


def test_login_throttling_after_five_failures(client):
    assert [login(client, "admin", "bad").status_code for _ in range(5)] == [401] * 5
    blocked = login(client, "admin", "bad")
    assert blocked.status_code == 429 and "Too many attempts" in blocked.text
    assert login(client).status_code == 429  # even the right password waits while throttled


def test_deactivated_account_is_denied(client, db):
    db.scalar(select(AdminAccount)).active = False
    db.commit()
    assert login(client).status_code == 403


def test_every_admin_page_needs_login(client, db):
    r = make_request(db)
    for url in ("/admin", "/admin/requests", f"/admin/requests/{r.id}", "/admin/services", "/admin/services/new",
                "/admin/customers", "/admin/reports", "/admin/team", "/admin/audit", "/admin/account", "/admin/export/requests.csv"):
        got = client.get(url)
        assert got.status_code == 303 and got.headers["location"] == "/admin/login", url
    assert client.post("/admin/requests/1/status", data={"status": "completed"}).status_code == 303


# ---------- sessions ----------
def test_logout_revokes_the_session_for_good(admin, db):
    token = admin.cookies.get("admin_session")
    assert admin.post("/admin/logout").status_code == 303
    stolen = new_client(); stolen.cookies.set("admin_session", token, path="/admin")
    assert stolen.get("/admin", follow_redirects=False).status_code == 303
    assert db.scalar(select(AdminSession)).revoked_at is not None and "auth.logout" in actions(db)


def test_idle_timeout_is_30_minutes(admin, db):
    row = db.scalar(select(AdminSession))
    row.last_seen_at = utcnow() - timedelta(minutes=29); db.commit()
    assert admin.get("/admin").status_code == 200
    db.expire_all(); row = db.scalar(select(AdminSession))
    row.last_seen_at = utcnow() - timedelta(minutes=31); db.commit()
    assert admin.get("/admin").status_code == 303


def test_absolute_lifetime_is_24_hours(admin, db):
    row = db.scalar(select(AdminSession))
    assert 23.9 < (row.expires_at.replace(tzinfo=utcnow().tzinfo) - utcnow()).total_seconds() / 3600 <= 24
    row.expires_at = utcnow() - timedelta(seconds=1); db.commit()
    assert admin.get("/admin").status_code == 303


def test_new_login_kills_the_old_cookie_session_fixation(client, db):
    login(client); first = client.cookies.get("admin_session")
    login(client); second = client.cookies.get("admin_session")
    assert first != second
    old = new_client(); old.cookies.set("admin_session", first, path="/admin")
    assert old.get("/admin").status_code == 303 and client.get("/admin").status_code == 200


def test_sessions_of_a_deactivated_admin_stop_working(admin, db):
    db.scalar(select(AdminAccount)).active = False; db.commit()
    assert admin.get("/admin").status_code == 303


# ---------- CSRF and cross-site ----------
def test_post_without_or_with_wrong_csrf_token_is_refused(admin, db, req):
    url = f"/admin/requests/{req.id}/status"
    assert admin.post(url, data={"status": "completed", "message": ""}).status_code == 403
    assert admin.post(url, data={"status": "completed", "message": "", "csrf_token": "0" * 64}).status_code == 403
    db.expire_all()
    from app.modules.requests.models import ServiceRequest
    assert db.get(ServiceRequest, req.id).status == "received"
    assert post(admin, url, {"status": "completed", "message": ""}).status_code == 303


def test_csrf_token_of_another_session_does_not_work(admin, db, req):
    other = new_client(); login(other)
    assert csrf(other) != csrf(admin)
    assert admin.post(f"/admin/requests/{req.id}/status", data={"status": "completed", "csrf_token": csrf(other)}).status_code == 403


def test_cross_site_posts_to_admin_are_blocked(admin):
    r = admin.post("/admin/account/password", data={"csrf_token": csrf(admin)}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and "Cross-site" in r.text


def test_security_headers(client, admin):
    for url in ("/", "/admin/login", "/admin"):
        h = (admin if url == "/admin" else client).get(url).headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in h["content-security-policy"]
        assert "script-src 'self'" in h["content-security-policy"] and "unsafe-inline" not in h["content-security-policy"]
    adm = admin.get("/admin").headers
    assert adm["cache-control"] == "no-store" and adm["x-robots-tag"] == "noindex"


def test_pages_have_no_inline_scripts_or_styles(client, admin, db, req):
    pages = [client.get("/"), client.get(f"/track/{req.code}"), client.get("/admin/login"), client.get("/admin/forgot-password")] + \
            [admin.get(u) for u in ("/admin", "/admin/requests", f"/admin/requests/{req.id}", "/admin/services/new", "/admin/team/new", "/admin/audit", "/admin/reports")]
    for p in pages:
        assert p.status_code == 200
        assert not re.search(r"<script(?![^>]*\bsrc=)", p.text) and 'style="' not in p.text and " onclick=" not in p.text and " onsubmit=" not in p.text


def test_errors_do_not_leak_internals(client, admin):
    for resp in (client.get("/nope"), admin.get("/admin/requests/999999")):
        assert resp.status_code == 404 and "Traceback" not in resp.text and "sqlalchemy" not in resp.text.lower()


def test_server_errors_show_a_reference_not_a_stack_trace(db):
    from fastapi.testclient import TestClient
    from app.main import app

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internals")
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == 500 and "secret internals" not in r.text and "Reference:" in r.text


# ---------- forgot / reset ----------
@pytest.fixture
def mailbox(monkeypatch):
    sent = []
    monkeypatch.setattr("app.modules.auth.router.send_reset_email", lambda to, link: sent.append((to, link)))
    return sent


def test_same_answer_for_known_and_unknown_email(client, mailbox):
    a = client.post("/admin/forgot-password", data={"email": "OWNER@example.com"})
    b = client.post("/admin/forgot-password", data={"email": "stranger@example.com"})
    c = client.post("/admin/forgot-password", data={"email": "not-an-email"})
    assert a.status_code == b.status_code == c.status_code == 200
    assert all("reset link is on its way" in r.text for r in (a, b, c))
    assert [to for to, _ in mailbox] == ["owner@example.com"]


def test_reset_link_is_hashed_expires_in_15_minutes_and_works_once(client, db, mailbox):
    client.post("/admin/forgot-password", data={"email": "owner@example.com"})
    token = mailbox[0][1].rsplit("/", 1)[1]
    row = db.scalar(select(PasswordReset))
    assert row.token_hash != token and len(row.token_hash) == 64
    assert 14 <= (row.expires_at.replace(tzinfo=utcnow().tzinfo) - utcnow()).total_seconds() / 60 <= 15.1
    assert client.get(f"/admin/reset-password/{token}").status_code == 200
    assert client.post(f"/admin/reset-password/{token}", data={"password": "short", "confirm": "short"}).status_code == 422
    assert client.post(f"/admin/reset-password/{token}", data={"password": "A-long-new-pass-1", "confirm": "different-long-1"}).status_code == 422
    ok = client.post(f"/admin/reset-password/{token}", data={"password": "A-long-new-pass-1", "confirm": "A-long-new-pass-1"})
    assert ok.status_code == 303 and ok.headers["location"] == "/admin/login"
    assert "Password updated" in client.get("/admin/login").text
    assert client.get(f"/admin/reset-password/{token}").status_code == 400
    assert client.post(f"/admin/reset-password/{token}", data={"password": "Another-long-pass-2", "confirm": "Another-long-pass-2"}).status_code == 400
    assert login(new_client(), password=ADMIN_PW).status_code == 401 and login(new_client(), password="A-long-new-pass-1").status_code == 303
    assert {"auth.password_reset_requested", "auth.password_reset_done"} <= set(actions(db))


def test_reset_signs_out_every_existing_session(client, db, mailbox):
    victim = new_client(); login(victim)
    assert victim.get("/admin").status_code == 200
    client.post("/admin/forgot-password", data={"email": "owner@example.com"})
    token = mailbox[0][1].rsplit("/", 1)[1]
    client.post(f"/admin/reset-password/{token}", data={"password": "A-long-new-pass-1", "confirm": "A-long-new-pass-1"})
    assert victim.get("/admin").status_code == 303


def test_expired_and_garbage_links_are_refused(client, db, mailbox):
    client.post("/admin/forgot-password", data={"email": "owner@example.com"})
    token = mailbox[0][1].rsplit("/", 1)[1]
    db.scalar(select(PasswordReset)).expires_at = utcnow() - timedelta(seconds=1); db.commit()
    assert client.get(f"/admin/reset-password/{token}").status_code == 400
    assert client.get("/admin/reset-password/not-a-token").status_code == 400


def test_a_new_reset_request_cancels_the_previous_link(client, db, mailbox):
    client.post("/admin/forgot-password", data={"email": "owner@example.com"})
    client.post("/admin/forgot-password", data={"email": "owner@example.com"})
    first, second = (m[1].rsplit("/", 1)[1] for m in mailbox)
    assert client.get(f"/admin/reset-password/{first}").status_code == 400 and client.get(f"/admin/reset-password/{second}").status_code == 200


def test_forgot_password_is_throttled(client, mailbox):
    for _ in range(5):
        client.post("/admin/forgot-password", data={"email": "x@example.com"})
    assert client.post("/admin/forgot-password", data={"email": "owner@example.com"}).status_code == 429 and mailbox == []


def test_reauthentication_is_throttled(admin, db):
    from app.modules.admin.models import AdminRole
    from app.modules.auth.models import AdminAccount
    role_id = db.scalar(select(AdminRole.id).where(AdminRole.name == "staff"))
    form = {"username": "locked", "full_name": "Locked Out", "email": "locked@example.com", "role_id": role_id,
            "password": "Temp-Password-1"}
    for _ in range(5):
        post(admin, "/admin/team", {**form, "current_password": "nope"})
    post(admin, "/admin/team", {**form, "current_password": ADMIN_PW})  # right password, but locked
    db.expire_all()
    assert db.scalar(select(AdminAccount).where(AdminAccount.username == "locked")) is None
