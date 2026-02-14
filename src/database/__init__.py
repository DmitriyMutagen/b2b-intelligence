"""Database package — engine, session, and models."""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL_SYNC = os.getenv(
    "DATABASE_URL_SYNC",
    "postgresql+psycopg2://marketai:marketai@localhost:5432/b2b_intelligence"
)

engine = create_engine(
    DATABASE_URL_SYNC,
    echo=False,
    pool_pre_ping=True,
    pool_timeout=5,
    connect_args={"connect_timeout": 5}
)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """Yield a DB session for FastAPI dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

