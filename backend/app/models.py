import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Enum, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import enum

from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    contracts = relationship("Contract", back_populates="user", cascade="all, delete-orphan")

class ContractStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class RiskLevel(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class Contract(Base):
    __tablename__ = "contracts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String, nullable=False)
    file_hash = Column(String, unique=True, index=True, nullable=True)
    status = Column(Enum(ContractStatus), default=ContractStatus.PENDING)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    
    # Store aggregated analysis like overall risk score, key obligations, etc.
    metadata_json = Column(JSONB, default={})
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    clauses = relationship("ContractClause", back_populates="contract", cascade="all, delete-orphan")
    user = relationship("User", back_populates="contracts")


class ContractClause(Base):
    __tablename__ = "contract_clauses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False)
    
    clause_type = Column(String, index=True) # e.g., "Indemnification", "Termination", "Payment Terms"
    text_content = Column(Text, nullable=False)
    
    # AI Risk Assessment
    risk_level = Column(Enum(RiskLevel), default=RiskLevel.LOW)
    risk_reasoning = Column(Text, nullable=True) # AI's explanation for the risk level
    redline_suggestion = Column(Text, nullable=True) # Suggested replacement text for risky clauses
    risk_debug_json = Column(JSONB, default={})  # Per-clause technical debug (dimension scores, confidence, model, latency)
    
    # 1536 is standard for OpenAI embeddings. Update to 768 if using local or some Gemini models.
    embedding = Column(Vector(1536)) 
    
    contract = relationship("Contract", back_populates="clauses")


class ContractEvent(Base):
    """
    Lightweight first-party tracing/logging for contract processing (Langfuse replacement).
    """
    __tablename__ = "contract_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False, index=True)

    event_type = Column(String, nullable=False)  # e.g. status, llm, error
    message = Column(Text, nullable=False)
    payload_json = Column(JSONB, default={})

    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ClauseFeedback(Base):
    """
    Phase 1 feedback loop — stores user corrections without re-scoring.
    Stories 013 & 014.
    """
    __tablename__ = "clause_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    contract_id = Column(UUID(as_uuid=True), ForeignKey("contracts.id"), nullable=False, index=True)
    clause_id = Column(UUID(as_uuid=True), ForeignKey("contract_clauses.id"), nullable=False, index=True)
    is_risky = Column(Boolean, nullable=False)  # True = user says risky; False = user says not risky
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
