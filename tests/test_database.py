import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from tests.conftest import make_request

ROOT = Path(__file__).resolve().parents[1]


def run_alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)


def test_migrations_upgrade_match_models_and_downgrade(tmp_path):
    url = f"sqlite:///{tmp_path}/m.db"
    assert run_alembic(url, "upgrade", "head").returncode == 0
    check = run_alembic(url, "check")
    assert check.returncode == 0, check.stderr + check.stdout  # models and migrations agree: no forgotten migration
    assert run_alembic(url, "downgrade", "base").returncode == 0
    assert run_alembic(url, "upgrade", "head").returncode == 0


def test_app_refuses_to_start_on_an_unmigrated_database(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    import app.main as main
    monkeypatch.setattr(main, "engine", create_engine(f"sqlite:///{tmp_path}/empty.db"))
    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        main.ensure_migrated()


def test_cli_reset_password_signs_everyone_out_and_reactivates(db):
    from sqlalchemy import select as sel
    from app.cli import reset_password
    from app.modules.auth.models import AdminAccount, AdminSession
    from tests.conftest import ADMIN_PW, login, new_client
    c = new_client(); login(c)
    owner = db.scalar(sel(AdminAccount)); owner.active = False; db.commit()
    assert reset_password(None, "short") == 1
    assert reset_password("nobody", "A-long-new-pass-1") == 1
    assert reset_password(None, "A-long-new-pass-1") == 0
    db.expire_all()
    assert db.scalar(sel(AdminAccount)).active and all(s.revoked_at for s in db.scalars(sel(AdminSession)))
    assert login(new_client(), password=ADMIN_PW).status_code == 401 and login(new_client(), password="A-long-new-pass-1").status_code == 303
