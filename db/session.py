"""
db/session.py
PostgreSQL connection and session factory.
"""
import json
import logging
from pathlib import Path
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool

from db.models import Base

logger = logging.getLogger(__name__)

_engine = None
_SessionFactory = None


def _load_config() -> dict:
    cfg_path = Path(__file__).parent.parent / "config.json"
    with open(cfg_path) as f:
        return json.load(f)


def init_db(config: dict | None = None) -> None:
    """
    Initialise the database engine and create all tables.
    Call once at application startup.
    """
    global _engine, _SessionFactory

    if config is None:
        config = _load_config()

    db_cfg = config["database"]

    # Use SQLAlchemy URL object to safely handle special characters
    # in passwords (e.g. @, #, %) without breaking the connection string
    from sqlalchemy.engine import URL
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=db_cfg["user"],
        password=db_cfg["password"],
        host=db_cfg["host"],
        port=db_cfg["port"],
        database=db_cfg["name"],
    )

    _engine = create_engine(
        url,
        poolclass=QueuePool,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        echo=False,
    )

    # Auto-create all tables defined in models
    Base.metadata.create_all(_engine)
    _SessionFactory = sessionmaker(bind=_engine, autoflush=True, autocommit=False)
    logger.info("Database initialised and tables created.")


def get_session() -> Session:
    """Return a new SQLAlchemy Session. Caller is responsible for commit/close."""
    if _SessionFactory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _SessionFactory()


@contextmanager
def session_scope():
    """
    Context manager that provides a transactional scope.
    Usage:
        with session_scope() as session:
            session.add(obj)
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    return _engine
