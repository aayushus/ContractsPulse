import os
import bcrypt
import jwt
import re
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import text

# OpenTelemetry Tracing Setup for Jaeger
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource

# Security & JWT settings
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-contractspulse-key-change-it")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week
DISABLE_SIGNUP = os.getenv("DISABLE_SIGNUP", "false").lower() in ("true", "1", "yes")

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return encoded_jwt

resource = Resource.create({"service.name": "contractspulse-api"})
provider = TracerProvider(resource=resource)
endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://jaeger:4317")
exporter = OTLPSpanExporter(endpoint=endpoint)
provider.add_span_processor(BatchSpanProcessor(exporter))
trace.set_tracer_provider(provider) 

app = FastAPI(
    title="ContractsPulse API",
    description="Backend API for Legal-Grade RAG and Contract Intelligence",
    version="0.1.0"
)

# CORS to allow SvelteKit frontend to communicate
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "ContractsPulse API is running"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

from .parser import extract_text_from_pdf, extract_contract_metadata, standardized_filename, compute_text_hash
from .agents import process_contract_text, process_contract_text_fallback, _heuristic_redline, _first_sentence, _heuristic_risk, _enrich_ip_clause
from .database import engine, Base, get_db
from .models import User, Contract, ContractClause, ContractStatus, RiskLevel, ContractEvent, ClauseFeedback

def get_current_user(
    authorization: str | None = Header(None),
    db: Session = Depends(get_db)
):
    # CLI compatibility fallback:
    # If the Authorization header is missing, fall back to the default seeded admin@admin.com user.
    # This allows unauthenticated API calls (like from the local CLI out-of-the-box) to function normally.
    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ")[1]
    
    if not token:
        admin_user = db.query(User).filter(User.email == "admin@admin.com").first()
        if not admin_user:
            raise HTTPException(
                status_code=401,
                detail="Not authenticated and default admin user not found.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return admin_user

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload.")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials.")

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found.")
    return user



class ContractTextIn(BaseModel):
    text: str


def log_contract_event(db: Session, contract_id: str, event_type: str, message: str, payload: dict | None = None):
    db.add(
        ContractEvent(
            contract_id=contract_id,
            event_type=event_type,
            message=message,
            payload_json=payload or {},
        )
    )


@app.post("/api/v1/contracts/text")
async def create_contract_from_text(
    payload: ContractTextIn,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw_text = (payload.text or "").strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="text is required")

    meta = extract_contract_metadata(raw_text)
    from datetime import datetime
    upload_date = datetime.utcnow().date().isoformat()
    std_name = standardized_filename(meta, upload_date)
    text_hash = compute_text_hash(raw_text)

    existing_contract = db.query(Contract).filter(Contract.file_hash == text_hash, Contract.user_id == current_user.id).first()
    if existing_contract:
        # Refresh metadata + filename each submission, but skip re-analysis if already processed.
        existing = existing_contract.metadata_json or {}
        existing_contract.filename = std_name
        existing_contract.metadata_json = {**existing, "raw_text": raw_text, **meta}

        if existing_contract.status == ContractStatus.FAILED:
            existing_contract.status = ContractStatus.PROCESSING
            log_contract_event(db, str(existing_contract.id), "ingest", "Text re-submitted; retrying failed analysis", {"cache": "hit", "mode": "text"})
            db.commit()
            background_tasks.add_task(analyze_contract_background, str(existing_contract.id), raw_text)
            return {
                "filename": existing_contract.filename,
                "contract_id": str(existing_contract.id),
                "status": "PROCESSING",
                "message": "Retrying failed contract analysis.",
            }

        log_contract_event(db, str(existing_contract.id), "ingest", "Text re-submitted; using cached result", {"cache": "hit", "mode": "text", "status": existing_contract.status.value})
        db.commit()
        return {
            "filename": existing_contract.filename,
            "contract_id": str(existing_contract.id),
            "status": existing_contract.status.value if existing_contract.status else "COMPLETED",
            "message": ("Contract already processing." if existing_contract.status == ContractStatus.PROCESSING else "Contract already processed."),
        }

    new_contract = Contract(
        filename=std_name,
        file_hash=text_hash,
        status=ContractStatus.PROCESSING,
        metadata_json={"raw_text": raw_text, **meta},
        user_id=current_user.id,
    )
    db.add(new_contract)
    log_contract_event(db, str(new_contract.id), "ingest", "Text submitted for analysis", {"cache": "miss", "mode": "text"})
    db.commit()
    db.refresh(new_contract)

    background_tasks.add_task(analyze_contract_background, str(new_contract.id), raw_text)

    return {
        "filename": new_contract.filename,
        "contract_id": str(new_contract.id),
        "status": new_contract.status.value,
        "message": "Analysis running in background.",
    }

@app.on_event("startup")
async def startup_event():
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
    
    # Remove unique index constraint on contracts.file_hash if it exists to allow per-user duplicate uploads
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE contracts DROP CONSTRAINT IF EXISTS uq_contracts_file_hash;"))
        conn.execute(text("DROP INDEX IF EXISTS ix_contracts_file_hash;"))
        
    Base.metadata.create_all(bind=engine)
    
    # Re-create index as non-unique
    with engine.begin() as conn:
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_contracts_file_hash ON contracts(file_hash);"))
        
    # Lightweight schema catch-up for additive columns (demo-friendly; avoids migrations).
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE contract_clauses "
                "ADD COLUMN IF NOT EXISTS risk_debug_json jsonb DEFAULT '{}'::jsonb;"
            )
        )
    # Ensure contracts has user_id
    with engine.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE contracts ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE CASCADE;"
            )
        )
    # Stories 013/014: ensure clause_feedback table exists.
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS clause_feedback ("
            "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "  contract_id uuid NOT NULL REFERENCES contracts(id) ON DELETE CASCADE, "
            "  clause_id uuid NOT NULL REFERENCES contract_clauses(id) ON DELETE CASCADE, "
            "  is_risky boolean NOT NULL, "
            "  note text, "
            "  created_at timestamptz NOT NULL DEFAULT now() "
            ");"
        ))
    
    # Seed default user if not exists
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        admin_exists = db.query(User).filter(User.email == "admin@admin.com").first()
        if not admin_exists:
            admin_hashed = get_password_hash("admin")
            default_admin = User(email="admin@admin.com", hashed_password=admin_hashed)
            db.add(default_admin)
            db.commit()
            print("Default admin user admin@admin.com created.")
    except Exception as e:
        print(f"Error seeding default user: {e}")
    finally:
        db.close()

def save_analysis_results(db: Session, contract_id: str, analysis_results: list):
    contract = db.query(Contract).filter(Contract.id == contract_id).first()
    if not contract:
        return
    
    # Track overall risk for metadata
    risk_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}

    severity = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    top_candidates = []

    def extract_auto_renewal_info(text: str) -> dict | None:
        t = (text or "")
        if not re.search(r"\b(auto[\s-]?renew|auto[\s-]?renewal|automatically renew|renewal term)\b", t, flags=re.I):
            return None
        days = None
        m = re.search(r"\b(\d{1,3})\s+days?\s+(?:prior\s+to|before)\b", t, flags=re.I)
        if m:
            try:
                days = int(m.group(1))
            except Exception:
                days = None
        return {"opt_out_days_before_renewal": days}
    
    for item in analysis_results:
        clause_data = item['clause']
        risk_data = item['analysis']

        auto_info = extract_auto_renewal_info(clause_data.text_content)
        effective_risk_level = risk_data.risk_level
        effective_reasoning = risk_data.risk_reasoning
        if auto_info and effective_risk_level == "LOW":
            effective_risk_level = "MEDIUM"
            effective_reasoning = (
                "Auto-renewal clause detected. Confirm the opt-out deadline to avoid unwanted renewals."
                if not (effective_reasoning or "").strip()
                else effective_reasoning
            )

        # Story 006: HIGH/CRITICAL must include (a) a copy/paste-ready one-sentence rationale and
        # (b) a suggested replacement (redline). If the LLM omitted these, fill deterministically.
        effective_redline = risk_data.redline_suggestion
        if effective_risk_level in {"HIGH", "CRITICAL"}:
            effective_reasoning = _first_sentence(
                effective_reasoning
                or "This clause shifts disproportionate risk; the suggested replacement narrows scope and adds market-standard protections."
            )
            if not (effective_redline or "").strip():
                effective_redline = _heuristic_redline(
                    clause_data.clause_type,
                    clause_data.text_content,
                    effective_risk_level,
                )
        elif (effective_reasoning or "").strip():
            effective_reasoning = effective_reasoning.strip()

        # Story 009: enforce plain-English side-project warning for broad IP assignment clauses.
        effective_risk_level, effective_reasoning, effective_redline = _enrich_ip_clause(
            clause_data.clause_type,
            clause_data.text_content,
            effective_risk_level,
            effective_reasoning,
            effective_redline,
        )
        
        clause = ContractClause(
            contract_id=contract_id,
            clause_type=clause_data.clause_type,
            text_content=clause_data.text_content,
            risk_level=RiskLevel(effective_risk_level),
            risk_reasoning=effective_reasoning,
            redline_suggestion=effective_redline,
            risk_debug_json=getattr(risk_data, "debug_json", {}) or {},
        )
        db.add(clause)
        
        if effective_risk_level in risk_counts:
            risk_counts[effective_risk_level] += 1

        top_candidates.append({
            "clause_type": clause_data.clause_type,
            "risk_level": effective_risk_level,
            "risk_reasoning": effective_reasoning,
            "text_excerpt": (clause_data.text_content or "")[:600],
            "auto_renewal": auto_info,
        })

    contract.status = ContractStatus.COMPLETED
    top_candidates.sort(key=lambda x: (severity.get(x["risk_level"], 0), len(x.get("risk_reasoning") or "")), reverse=True)
    top_risks = top_candidates[:3]
    existing = contract.metadata_json or {}
    contract.metadata_json = {**existing, "risk_counts": risk_counts, "top_risks": top_risks}
    db.commit()

async def analyze_contract_background(contract_id: str, raw_text: str):
    print(f"Background task started for contract: {contract_id}")
    
    try:
        # Define callback to update detailed step
        async def update_status(step_msg: str):
            from .database import SessionLocal
            db_tmp = SessionLocal()
            try:
                c = db_tmp.query(Contract).filter(Contract.id == contract_id).first()
                if c:
                    existing = c.metadata_json or {}
                    c.metadata_json = {**existing, "processing_step": step_msg}
                    log_contract_event(db_tmp, contract_id, "status", step_msg)
                    db_tmp.commit()
            finally:
                db_tmp.close()

        # 1. Run the Pydantic AI graph.
        # Guard against provider/network hangs so contracts don't sit in PROCESSING forever.
        import asyncio
        timeout_s = float(os.getenv("CONTRACT_ANALYSIS_TIMEOUT_S", "60"))
        try:
            from .database import SessionLocal
            db0 = SessionLocal()
            try:
                log_contract_event(db0, contract_id, "analysis", "LLM analysis started", {"timeout_s": timeout_s})
                db0.commit()
            finally:
                db0.close()
            analysis_results = await asyncio.wait_for(
                process_contract_text(raw_text, update_status),
                timeout=timeout_s,
            )
            analysis_meta = {"analysis_mode": "llm"}
        except asyncio.TimeoutError:
            from .database import SessionLocal
            db0 = SessionLocal()
            try:
                log_contract_event(db0, contract_id, "analysis", "LLM timed out; using heuristic fallback", {"timeout_s": timeout_s})
                db0.commit()
            finally:
                db0.close()
            # Provider/network hang; fall back to deterministic processing so the pipeline completes.
            analysis_results = await process_contract_text_fallback(raw_text, update_status)
            analysis_meta = {"analysis_mode": "heuristic_fallback", "llm_timeout_s": timeout_s}
        
        # 2. Save to DB (Postgres/pgvector)
        from .database import SessionLocal
        db = SessionLocal()
        try:
            save_analysis_results(db, contract_id, analysis_results)
            # Mark which analysis mode was used.
            contract = db.query(Contract).filter(Contract.id == contract_id).first()
            if contract:
                existing = contract.metadata_json or {}
                contract.metadata_json = {**existing, **analysis_meta}
                log_contract_event(db, contract_id, "analysis", "Analysis completed", analysis_meta)
                db.commit()
            print(f"Background task complete. Saved {len(analysis_results)} clauses.")
        finally:
            db.close()
            
    except Exception as e:
        print(f"Error in background task: {e}")
        from .database import SessionLocal
        db = SessionLocal()
        try:
            contract = db.query(Contract).filter(Contract.id == contract_id).first()
            if contract:
                # asyncio.TimeoutError stringifies to "" so make it explicit.
                try:
                    import asyncio
                    is_timeout = isinstance(e, asyncio.TimeoutError)
                except Exception:
                    is_timeout = False

                timeout_s = os.getenv("CONTRACT_ANALYSIS_TIMEOUT_S", "60")
                contract.status = ContractStatus.FAILED
                existing = contract.metadata_json or {}
                contract.metadata_json = {
                    **existing,
                    "processing_step": f"Failed: {type(e).__name__}",
                    "error": (f"Timed out after {timeout_s}s" if is_timeout else (str(e) or type(e).__name__)),
                }
                log_contract_event(db, contract_id, "error", "Analysis failed", {"error": contract.metadata_json.get("error")})
                db.commit()
        finally:
            db.close()


@app.get("/api/v1/contracts/{contract_id}/events")
async def get_contract_events(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Verify contract ownership
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
        
    events = (
        db.query(ContractEvent)
        .filter(ContractEvent.contract_id == contract_id)
        .order_by(ContractEvent.created_at.desc())
        .limit(200)
        .all()
    )
    return {
        "events": [
            {
                "id": str(e.id),
                "contract_id": str(e.contract_id),
                "event_type": e.event_type,
                "message": e.message,
                "payload_json": e.payload_json,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    }


@app.get("/api/v1/events/recent")
async def get_recent_events(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Join with Contract to retrieve only events generated by contracts owned by current_user
    events = (
        db.query(ContractEvent)
        .join(Contract, ContractEvent.contract_id == Contract.id)
        .filter(Contract.user_id == current_user.id)
        .order_by(ContractEvent.created_at.desc())
        .limit(200)
        .all()
    )
    return {
        "events": [
            {
                "id": str(e.id),
                "contract_id": str(e.contract_id),
                "event_type": e.event_type,
                "message": e.message,
                "payload_json": e.payload_json,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
    }

@app.post("/api/v1/contracts/upload")
async def upload_contract(
    background_tasks: BackgroundTasks, 
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Read bytes
    file_bytes = await file.read()
    
    # 2. Extract Text and Hash
    file_hash, raw_text = extract_text_from_pdf(file_bytes)
    meta = extract_contract_metadata(raw_text)
    from datetime import datetime
    upload_date = datetime.utcnow().date().isoformat()
    std_name = standardized_filename(meta, upload_date)
    
    # Check if exists (specifically owned by current_user)
    existing_contract = db.query(Contract).filter(Contract.file_hash == file_hash, Contract.user_id == current_user.id).first()
    if existing_contract:
        # Always refresh filename/metadata on upload (user requested regeneration every time).
        existing = existing_contract.metadata_json or {}
        existing_contract.filename = std_name
        existing_contract.metadata_json = {**existing, "raw_text": raw_text, **meta}
        if existing_contract.status == ContractStatus.FAILED:
            # Retry processing for failed contracts
            existing_contract.status = ContractStatus.PROCESSING
            log_contract_event(db, str(existing_contract.id), "ingest", "PDF re-uploaded; retrying failed analysis", {"cache": "hit", "mode": "pdf"})
            db.commit()
            background_tasks.add_task(analyze_contract_background, str(existing_contract.id), raw_text)
            return {
                "filename": existing_contract.filename,
                "contract_id": str(existing_contract.id),
                "status": "PROCESSING",
                "message": "Retrying failed contract analysis."
            }
        else:
            log_contract_event(db, str(existing_contract.id), "ingest", "PDF re-uploaded; using cached result", {"cache": "hit", "mode": "pdf", "status": existing_contract.status.value})
            db.commit()
            return {
                "filename": existing_contract.filename,
                "contract_id": str(existing_contract.id),
                "status": existing_contract.status.value if existing_contract.status else "COMPLETED",
                "message": ("Contract already processing." if existing_contract.status == ContractStatus.PROCESSING else "Contract already processed."),
            }
    
    # 3. Create Contract Record
    new_contract = Contract(
        filename=std_name,
        file_hash=file_hash,
        status=ContractStatus.PROCESSING,
        metadata_json={"raw_text": raw_text, **meta},
        user_id=current_user.id
    )
    db.add(new_contract)
    log_contract_event(db, str(new_contract.id), "ingest", "PDF uploaded for analysis", {"cache": "miss", "mode": "pdf"})
    db.commit()
    db.refresh(new_contract)
    
    # 4. Dispatch to background worker
    background_tasks.add_task(analyze_contract_background, str(new_contract.id), raw_text)
    
    return {
        "filename": new_contract.filename, 
        "contract_id": str(new_contract.id),
        "status": new_contract.status,
        "message": "Analysis running in background."
    }

@app.post("/api/v1/contracts/{contract_id}/reprocess")
async def reprocess_contract(
    contract_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
        
    raw_text = contract.metadata_json.get("raw_text")
    if not raw_text:
        raise HTTPException(status_code=400, detail="Raw text not available. Please re-upload.")
        
    # Wipe existing clauses
    db.query(ContractClause).filter(ContractClause.contract_id == contract_id).delete()
    
    from datetime import datetime
    meta = extract_contract_metadata(raw_text)
    upload_date = datetime.utcnow().date().isoformat()
    contract.filename = standardized_filename(meta, upload_date)

    contract.status = ContractStatus.PROCESSING
    # Keep raw_text + extracted naming metadata, clear analysis outputs.
    contract.metadata_json = {"raw_text": raw_text, **meta}
    log_contract_event(db, str(contract.id), "ingest", "Reprocess requested", {"mode": "reprocess"})
    db.commit()
    
    background_tasks.add_task(analyze_contract_background, str(contract.id), raw_text)
    
    return {"message": "Reprocessing started", "status": "PROCESSING"}

@app.delete("/api/v1/contracts/{contract_id}")
async def delete_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
        
    db.delete(contract)
    db.commit()
    return {"message": "Contract deleted successfully"}

@app.get("/api/v1/contracts/{contract_id}/status")
async def contract_status(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Story 008: lightweight polling endpoint for job status + best-effort ETA.
    (Also useful for a future CLI status command.)
    """
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    step = (contract.metadata_json or {}).get("processing_step") or ""

    def stage_from_step(s: str) -> dict:
        t = (s or "").lower()
        # 3-stage pipeline: Planning -> Thinking -> Executing
        if "segment" in t or "extract" in t:
            return {"key": "planning", "label": "Planning", "index": 1, "count": 3}
        if "analyz" in t or "risk" in t:
            return {"key": "thinking", "label": "Thinking", "index": 2, "count": 3}
        if "sav" in t:
            return {"key": "executing", "label": "Executing", "index": 3, "count": 3}
        return {"key": "processing", "label": "Processing", "index": 0, "count": 3}

    stage = stage_from_step(step)

    progress = None
    m = re.search(r"Clause\s+(\d+)\s+of\s+(\d+)", step, flags=re.I)
    if m:
        try:
            cur = int(m.group(1))
            total = int(m.group(2))
            if total > 0:
                progress = {"current": cur, "total": total, "ratio": max(0.0, min(1.0, cur / total))}
        except Exception:
            progress = None

    eta_seconds = None
    if contract.status == ContractStatus.PROCESSING:
        # Best-effort ETA: if we're in per-clause analysis, estimate from observed per-clause rate.
        if progress and progress.get("total") and progress.get("current"):
            cur = int(progress["current"])
            total = int(progress["total"])
            # Find recent analyzing events with clause counters.
            events = (
                db.query(ContractEvent)
                .filter(ContractEvent.contract_id == contract.id, ContractEvent.event_type == "status")
                .order_by(ContractEvent.created_at.asc())
                .limit(500)
                .all()
            )
            points = []
            for e in events:
                mm = re.search(r"Clause\s+(\d+)\s+of\s+(\d+)", e.message or "", flags=re.I)
                if not mm:
                    continue
                try:
                    i = int(mm.group(1))
                    n = int(mm.group(2))
                except Exception:
                    continue
                if n != total:
                    continue
                if i <= 0 or i > total:
                    continue
                points.append((e.created_at, i))

            if len(points) >= 2:
                t0, i0 = points[0]
                t1, i1 = points[-1]
                dt = max(0.001, (t1 - t0).total_seconds())
                di = max(1, i1 - i0)
                rate = di / dt  # clauses/sec
                remaining = max(0, total - cur)
                eta_seconds = int(round(remaining / max(0.01, rate)))
            else:
                # Default to a conservative 2s/clause if we have no timing history yet.
                remaining = max(0, total - cur)
                eta_seconds = int(remaining * 2)
        else:
            # Coarse ETA when we don't have a clause counter.
            if stage["key"] == "planning":
                eta_seconds = 10
            elif stage["key"] == "executing":
                eta_seconds = 3
            else:
                eta_seconds = 20

    return {
        "contract_id": str(contract.id),
        "status": contract.status.value if hasattr(contract.status, "value") else str(contract.status),
        "stage": stage,
        "processing_step": step or None,
        "progress": progress,
        "eta_seconds": eta_seconds,
        "created_at": contract.created_at.isoformat() if contract.created_at else None,
        "updated_at": contract.updated_at.isoformat() if contract.updated_at else None,
    }

@app.get("/api/v1/contracts/{contract_id}/clauses")
async def get_contract_clauses(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
        
    clauses = db.query(ContractClause).filter(ContractClause.contract_id == contract_id).all()
    
    return {
        "contract": {
            "id": str(contract.id),
            "filename": contract.filename,
            "status": contract.status,
            "metadata": contract.metadata_json
        },
        "clauses": [
            {
                "id": str(c.id),
                "clause_type": c.clause_type,
                "text_content": c.text_content,
                "risk_level": c.risk_level.value if c.risk_level else "LOW",
                "risk_reasoning": (
                    _first_sentence(c.risk_reasoning)
                    if (c.risk_level and c.risk_level.value in {"HIGH", "CRITICAL"} and (c.risk_reasoning or "").strip())
                    else c.risk_reasoning
                ),
                "redline_suggestion": (
                    c.redline_suggestion
                    if (c.redline_suggestion or "").strip()
                    else (
                        _heuristic_redline(
                            c.clause_type,
                            c.text_content,
                            c.risk_level.value if c.risk_level else "LOW",
                        )
                        if (c.risk_level and c.risk_level.value in {"HIGH", "CRITICAL"})
                        else None
                    )
                ),
                # Backfill technical details for older clauses that predate Story 007 (no LLM call).
                "risk_debug_json": (
                    (c.risk_debug_json or {})
                    if (c.risk_debug_json or {})
                    else (_heuristic_risk(c.clause_type, c.text_content).debug_json or {})
                ),
            } for c in clauses
        ]
    }

@app.get("/api/v1/contracts")
async def list_contracts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Fetch recent contracts ordered by creation date, strictly scoped to current_user
    contracts = (
        db.query(Contract)
        .filter(Contract.user_id == current_user.id)
        .order_by(Contract.created_at.desc())
        .limit(20)
        .all()
    )
    
    result = []
    for c in contracts:
        # Determine overall risk score from metadata
        overall_risk = "LOW"
        risk_counts = c.metadata_json.get("risk_counts", {})
        if risk_counts.get("CRITICAL", 0) > 0:
            overall_risk = "CRITICAL"
        elif risk_counts.get("HIGH", 0) > 0:
            overall_risk = "HIGH"
        elif risk_counts.get("MEDIUM", 0) > 0:
            overall_risk = "MEDIUM"

        result.append({
            "id": str(c.id),
            "filename": c.filename,
            "status": c.status.value,
            "metadata_json": c.metadata_json,
            "overall_risk": overall_risk if c.status == ContractStatus.COMPLETED else None,
            "created_at": c.created_at.isoformat()
        })

    return {"contracts": result}


# ---------------------------------------------------------------------------
# Story 011 / 012: Structured report endpoint (used by CLI analyze + report)
# ---------------------------------------------------------------------------

def _compute_overall_risk(risk_counts: dict) -> str:
    if risk_counts.get("CRITICAL", 0) > 0:
        return "CRITICAL"
    if risk_counts.get("HIGH", 0) > 0:
        return "HIGH"
    if risk_counts.get("MEDIUM", 0) > 0:
        return "MEDIUM"
    return "LOW"


def _one_line_summary(overall_risk: str, risk_counts: dict, top_risks: list) -> str:
    """Story 011: generate a one-line routing summary."""
    total_flagged = risk_counts.get("CRITICAL", 0) + risk_counts.get("HIGH", 0)
    if total_flagged == 0:
        return "No high-risk clauses detected; routine review recommended before signing."
    clause_types = [r.get("clause_type", "") for r in top_risks if r.get("risk_level") in {"HIGH", "CRITICAL"}]
    types_str = ", ".join(clause_types[:3]) if clause_types else "flagged clauses"
    return (
        f"This contract contains {total_flagged} high-risk clause{'s' if total_flagged != 1 else ''} "
        f"({types_str}) requiring legal review before signing."
    )


@app.get("/api/v1/contracts/{contract_id}/report")
async def get_contract_report(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Structured report for CLI display (Story 011) and PDF export (Story 012).
    Returns overall risk, one-line summary, and flagged clauses (HIGH + CRITICAL).
    """
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract.status != ContractStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Contract analysis is not complete (status: {contract.status.value})")

    meta = contract.metadata_json or {}
    risk_counts = meta.get("risk_counts", {})
    top_risks = meta.get("top_risks", [])
    overall_risk = _compute_overall_risk(risk_counts)
    summary = _one_line_summary(overall_risk, risk_counts, top_risks)

    clauses = (
        db.query(ContractClause)
        .filter(ContractClause.contract_id == contract_id)
        .all()
    )

    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    flagged = sorted(
        [c for c in clauses if c.risk_level and c.risk_level.value in {"HIGH", "CRITICAL"}],
        key=lambda c: severity_order.get(c.risk_level.value, 9),
    )

    def _resolve_redline(c: ContractClause) -> str | None:
        if (c.redline_suggestion or "").strip():
            return c.redline_suggestion
        if c.risk_level and c.risk_level.value in {"HIGH", "CRITICAL"}:
            return _heuristic_redline(c.clause_type, c.text_content, c.risk_level.value)
        return None

    return {
        "contract_id": contract_id,
        "filename": contract.filename,
        "overall_risk": overall_risk,
        "risk_counts": risk_counts,
        "summary": summary,
        "flagged_clauses": [
            {
                "id": str(c.id),
                "clause_type": c.clause_type,
                "risk_level": c.risk_level.value,
                "risk_reasoning": (
                    _first_sentence(c.risk_reasoning)
                    if (c.risk_reasoning or "").strip()
                    else None
                ),
                "redline_suggestion": _resolve_redline(c),
                "text_excerpt": (c.text_content or "")[:800],
            }
            for c in flagged
        ],
    }


# ---------------------------------------------------------------------------
# Stories 013 & 014: Feedback endpoint
# ---------------------------------------------------------------------------

class FeedbackIn(BaseModel):
    is_risky: bool
    note: str | None = None


@app.post("/api/v1/feedback/{contract_id}/{clause_id}")
async def submit_feedback(
    contract_id: str,
    clause_id: str,
    payload: FeedbackIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Record a user correction without re-scoring. Stories 013 & 014.
    Returns a one-line confirmation and the feedback ID.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    clause = db.query(ContractClause).filter(
        ContractClause.id == clause_id,
        ContractClause.contract_id == contract_id,
    ).first()
    if not clause:
        raise HTTPException(status_code=404, detail="Clause not found")

    feedback = ClauseFeedback(
        contract_id=contract_id,
        clause_id=clause_id,
        is_risky=payload.is_risky,
        note=payload.note,
    )
    db.add(feedback)
    log_contract_event(
        db,
        contract_id,
        "feedback",
        f"Feedback recorded: clause {clause_id} marked {'risky' if payload.is_risky else 'not-risky'}",
        {"clause_id": clause_id, "is_risky": payload.is_risky, "note": payload.note},
    )
    db.commit()
    db.refresh(feedback)

    label = "risky" if payload.is_risky else "not-risky"
    return {
        "feedback_id": str(feedback.id),
        "message": f"Feedback recorded: clause marked {label}.",
    }


# ---------------------------------------------------------------------------
# User Stories 011: Auth Schemas and Endpoints
# ---------------------------------------------------------------------------

class UserSignupIn(BaseModel):
    email: str
    password: str

class UserLoginIn(BaseModel):
    email: str
    password: str

@app.get("/api/v1/auth/signup-status")
async def signup_status():
    return {"signup_disabled": DISABLE_SIGNUP}

@app.post("/api/v1/auth/signup")
async def signup(payload: UserSignupIn, db: Session = Depends(get_db)):
    if DISABLE_SIGNUP:
        raise HTTPException(status_code=403, detail="User registration is currently disabled.")
    
    # Normalise email: strip and lower
    email_clean = (payload.email or "").strip().lower()
    if not email_clean or "@" not in email_clean:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    
    if len(payload.password or "") < 4:
        raise HTTPException(status_code=400, detail="Password must be at least 4 characters long.")

    existing = db.query(User).filter(User.email == email_clean).first()
    if existing:
        raise HTTPException(status_code=400, detail="A user with this email already exists.")
    
    hashed = get_password_hash(payload.password)
    user = User(email=email_clean, hashed_password=hashed)
    db.add(user)
    db.commit()
    db.refresh(user)
    
    token = create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email
        }
    }

@app.post("/api/v1/auth/login")
async def login(payload: UserLoginIn, db: Session = Depends(get_db)):
    email_clean = (payload.email or "").strip().lower()
    user = db.query(User).filter(User.email == email_clean).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    
    token = create_access_token(data={"sub": str(user.id)}, expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email
        }
    }

@app.get("/api/v1/auth/me")
async def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email
    }
