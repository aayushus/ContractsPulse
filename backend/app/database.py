import os
from sqlalchemy import create_engine
from sqlalchemy import event
from sqlalchemy.orm import sessionmaker, declarative_base
from pgvector.psycopg2 import register_vector

# The docker-compose URL is postgresql://postgres:postgres@db:5432/contractspulse
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/contractspulse")

engine = create_engine(DATABASE_URL)

# Ensure pgvector binds work reliably across pooled connections.
@event.listens_for(engine, "connect")
def _register_pgvector(dbapi_connection, _connection_record):
    try:
        register_vector(dbapi_connection)
    except Exception:
        # Non-fatal: server may not have pgvector extension yet at connect-time.
        pass

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
