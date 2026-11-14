from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


_is_sqlite = settings.database_url.startswith("sqlite")
engine = create_engine(settings.database_url, pool_pre_ping=True,
                       connect_args={"check_same_thread": False} if _is_sqlite else {})

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _):  # SQLite ignores foreign keys unless asked
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()  # one transaction per request: roll back on any error
        raise
    finally:
        db.close()
