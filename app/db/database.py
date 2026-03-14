"""
database.py
-----------
Database connection layer.

Creates a SQLAlchemy engine and session factory from environment variables.
The get_db() function is used as a FastAPI dependency — it opens a session
for each request and closes it when the request is done.

Usage in routers:
    from app.db.database import get_db
    from sqlalchemy.orm import Session

    @router.get("/example")
    def example(db: Session = Depends(get_db)):
        ...
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Build connection URL from environment variables
# ---------------------------------------------------------------------------

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_NAME = os.getenv("DB_NAME", "geo_services")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")

DATABASE_URL = (
    f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# ---------------------------------------------------------------------------
# Engine and session factory
# ---------------------------------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # test connection before using it from the pool
    pool_size=10,         # number of connections to keep open
    max_overflow=20,      # extra connections allowed under load
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ---------------------------------------------------------------------------
# Dependency — used in every router via Depends(get_db)
# ---------------------------------------------------------------------------

def get_db() -> Session:
    """
    FastAPI dependency that provides a database session per request.

    Opens a session at the start of the request and guarantees it is
    closed when the request finishes — even if an exception is raised.

    Example:
        @router.get("/boundaries")
        def get_boundaries(db: Session = Depends(get_db)):
            repo = BoundaryRepository(db)
            return repo.get_countries()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
