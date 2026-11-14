"""Test setup. Uses TEST_DATABASE_URL / TEST_REDIS_URL when set (PostgreSQL, Redis), otherwise SQLite and in-memory limits."""
import os
import re
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["REDIS_URL"] = os.environ.get("TEST_REDIS_URL", "")
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "Test-Admin-Pass-123"
os.environ["ADMIN_EMAIL"] = "owner@example.com"
os.environ["ADMIN_FULL_NAME"] = "Owner"  # tests must not depend on the developer's own .env
os.environ["APP_ENV"] = "development"

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ADMIN_PW = "Test-Admin-Pass-123"


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")  # tests always run on the real migrations, never on create_all
    yield


@pytest.fixture(autouse=True)
def clean_db(migrated_database):
    from app.core.database import Base, SessionLocal
    from app.main import startup_seed
    from app.modules.auth import limits
    limits.clear_all()
    startup_seed()
    yield
    with SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            if table.name != "alembic_version":
                db.execute(delete(table))
        db.commit()


@pytest.fixture
def db():
    from app.core.database import SessionLocal
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app, follow_redirects=False) as c:
        yield c


def new_client():
    from app.main import app
    return TestClient(app, follow_redirects=False)


def login(c, username="admin", password=ADMIN_PW):
    return c.post("/admin/login", data={"username": username, "password": password})


@pytest.fixture
def admin(client):
    assert login(client).status_code == 303
    return client


def csrf(c) -> str:
    return re.search(r'name="csrf_token" value="([0-9a-f]+)"', c.get("/admin/account").text).group(1)


def post(c, url, data=None, **kw):
    """POST a form as a logged-in admin, adding the CSRF token."""
    return c.post(url, data={**(data or {}), "csrf_token": csrf(c)}, **kw)


def make_admin(db, username, role="staff", password="Staff-Pass-12345", email=""):
    from app.core.security import hash_password
    from app.modules.admin.models import AdminRole
    from app.modules.auth.models import AdminAccount
    acct = AdminAccount(username=username, full_name=username.title(), email=email, password_hash=hash_password(password),
                        role_id=db.scalar(select(AdminRole.id).where(AdminRole.name == role)))
    db.add(acct)
    db.commit()
    return acct


def logged_in(db, username, role, password="Staff-Pass-12345"):
    make_admin(db, username, role, password)
    c = new_client()
    assert login(c, username, password).status_code == 303
    return c


def make_request(db, slug="kra-itax", name="Jane Doe", phone="0712345678", details="Please help"):
    from app.modules.requests.service import create_request
    return create_request(db, slug, name, phone, details)


@pytest.fixture
def req(db):
    return make_request(db)
