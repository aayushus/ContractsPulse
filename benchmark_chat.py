import time
import asyncio
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.types import JSON as JSONB
try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    # Dummy Vector
    class Vector:
        pass

Base = declarative_base()

class Contract(Base):
    __tablename__ = 'contracts'
    id = Column(Integer, primary_key=True)
    metadata_json = Column(JSONB)

class ContractClause(Base):
    __tablename__ = 'contract_clauses'
    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey('contracts.id'))
    text_content = Column(String)
    embedding = Column(String) # Mocking as string for this benchmark if vector not available

# create dummy sqlite db to mock behaviour
engine = create_engine('sqlite:///:memory:')
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)
session = Session()

# Add a contract and 1000 clauses
contract = Contract(id=1)
session.add(contract)
session.commit()

clauses = [ContractClause(contract_id=1, text_content=f"Clause {i}") for i in range(5000)]
# no embeddings
session.add_all(clauses)
session.commit()

# Current method
def current_method():
    clauses = session.query(ContractClause).filter(ContractClause.contract_id == contract.id).all()
    has_embeddings = any(getattr(c, "embedding", None) is not None for c in clauses)
    return clauses, has_embeddings

# New method
def new_method():
    has_embeddings = session.query(
        session.query(ContractClause).filter(
            ContractClause.contract_id == contract.id,
            ContractClause.embedding.isnot(None)
        ).exists()
    ).scalar()
    # In worst case (no embeddings), we also fetch clauses
    clauses = []
    if not has_embeddings:
        clauses = session.query(ContractClause).filter(ContractClause.contract_id == contract.id).all()
    return clauses, has_embeddings


# Let's benchmark
t0 = time.time()
for _ in range(100):
    current_method()
t1 = time.time()
print(f"Current method (worst case): {t1-t0:.4f}s")

t0 = time.time()
for _ in range(100):
    new_method()
t1 = time.time()
print(f"New method (worst case): {t1-t0:.4f}s")

# Let's add embeddings and see best case
for c in session.query(ContractClause).all():
    c.embedding = "vector"
session.commit()

t0 = time.time()
for _ in range(100):
    current_method()
t1 = time.time()
print(f"Current method (best case): {t1-t0:.4f}s")

t0 = time.time()
for _ in range(100):
    new_method()
t1 = time.time()
print(f"New method (best case): {t1-t0:.4f}s")
