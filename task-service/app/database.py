import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# The connection string comes from the environment (set locally in the shell,
# and by Kubernetes later). It is never hard-coded in the source code.
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL environment variable is not set. "
        "Expected format: postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME"
    )

# pool_pre_ping checks a pooled connection is still alive before using it,
# e.g. after the PostgreSQL container/pod has been restarted.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: one database session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
