import logging
from contextlib import contextmanager
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from etl.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Engine placeholder
_engine = None
_SessionFactory = None

def get_engine(db_url: str = None):
    global _engine
    url = db_url or DATABASE_URL
    if _engine is None or str(_engine.url) != url:
        _engine = create_engine(url, pool_pre_ping=True)
    return _engine

def get_session_factory(db_url: str = None):
    global _SessionFactory
    engine = get_engine(db_url)
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return _SessionFactory

@contextmanager
def get_db_session(db_url: str = None) -> Generator[Session, None, None]:
    """Context manager for a single transactional session."""
    factory = get_session_factory(db_url)
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def check_db_connection(db_url: str = None) -> bool:
    """Test if database is reachable."""
    try:
        engine = get_engine(db_url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.warning(f"Database connection check failed: {e}")
        return False
