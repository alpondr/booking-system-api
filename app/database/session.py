from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(settings.database_url)

# Each request gets its own session from this factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: opens a DB session, gives it to the endpoint,
    and always closes it afterwards (even if the endpoint raises)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
