import os
import bcrypt
import jwt
import re
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
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
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise ValueError("JWT_SECRET environment variable must be set for security reasons.")
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7 # 1 week
def is_signup_disabled() -> bool:
    # Read dynamically so docker `.env` changes take effect after container restart,
    # and so `uvicorn --reload` doesn't accidentally keep stale module-level state.
    return os.getenv("DISABLE_SIGNUP", "false").lower().strip() in ("true", "1", "yes")


def _openai_chat_model() -> str:
    # Used by direct OpenAI calls in this module (not pydantic-ai Agents).
    return (os.getenv("OPENAI_MODEL_CHAT") or "gpt-5.4").strip()


def _openai_assistant_model() -> str:
    return (os.getenv("OPENAI_MODEL_ASSISTANT") or _openai_chat_model()).strip()

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
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:5173")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
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
from .agents import process_contract_text, process_contract_text_fallback, _heuristic_redline, _first_sentence, _heuristic_risk, _enrich_ip_clause, verify_previous_redlines, extract_contract_obligations
from .database import engine, Base, get_db
from .models import User, Contract, ContractClause, ContractStatus, RiskLevel, ContractEvent, ClauseFeedback, ContractReminder, ContractTemplate

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
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

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
    parent_id: str | None = None,
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

    # Bypass cache if it's a version revision upload
    existing_contract = None
    if not parent_id:
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

    # Version chaining support
    metadata = {"raw_text": raw_text, **meta}
    parent_contract = None
    version_number = 1
    if parent_id:
        parent_contract = db.query(Contract).filter(Contract.id == parent_id, Contract.user_id == current_user.id).first()
        if parent_contract:
            parent_version = parent_contract.metadata_json.get("version_number", 1) if parent_contract.metadata_json else 1
            version_number = parent_version + 1
            metadata["parent_contract_id"] = parent_id
            metadata["version_number"] = version_number

    new_contract = Contract(
        filename=std_name,
        file_hash=text_hash,
        status=ContractStatus.PROCESSING,
        metadata_json=metadata,
        user_id=current_user.id,
    )
    db.add(new_contract)
    db.flush()
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
        conn.execute(
            text(
                "ALTER TABLE contract_clauses "
                "ADD COLUMN IF NOT EXISTS embedding vector(1536);"
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

    # Renewal/notice automation: reminders
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS contract_reminders ("
            "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
            "  contract_id uuid NOT NULL REFERENCES contracts(id) ON DELETE CASCADE, "
            "  reminder_type text NOT NULL, "
            "  status text NOT NULL DEFAULT 'OPEN', "
            "  due_date timestamptz NOT NULL, "
            "  title text NOT NULL, "
            "  body text, "
            "  letter_json jsonb DEFAULT '{}'::jsonb, "
            "  created_at timestamptz NOT NULL DEFAULT now() "
            ");"
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_contract_reminders_user_due ON contract_reminders(user_id, due_date);"))

    # Contract template library
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE IF NOT EXISTS contract_templates ("
            "  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE, "
            "  name text NOT NULL, "
            "  description text, "
            "  raw_text text NOT NULL, "
            "  created_at timestamptz NOT NULL DEFAULT now() "
            ");"
        ))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_contract_templates_user_created ON contract_templates(user_id, created_at);"))

    # New feature: ensure contracts metadata can store expiry/obligations (stored in JSONB, no schema change needed)
    # No additional columns needed - all stored in metadata_json JSONB
    pass

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

async def _run_analysis_pipeline(contract_id: str, raw_text: str, update_status):
    import asyncio
    import os
    from .database import SessionLocal
    from .agents import process_contract_text, process_contract_text_fallback

    timeout_s = float(os.getenv("CONTRACT_ANALYSIS_TIMEOUT_S", "60"))
    try:
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
        db0 = SessionLocal()
        try:
            log_contract_event(db0, contract_id, "analysis", "LLM timed out; using heuristic fallback", {"timeout_s": timeout_s})
            db0.commit()
        finally:
            db0.close()
        # Provider/network hang; fall back to deterministic processing so the pipeline completes.
        analysis_results = await process_contract_text_fallback(raw_text, update_status)
        analysis_meta = {"analysis_mode": "heuristic_fallback", "llm_timeout_s": timeout_s}
    return analysis_results, analysis_meta


async def _generate_clause_embeddings(db, contract, contract_id: str):
    import os
    from .models import ContractClause
    existing = contract.metadata_json or {}
    try:
        existing["processing_step"] = "Generating clause embeddings for semantic search..."
        contract.metadata_json = existing
        db.commit()

        clauses = db.query(ContractClause).filter(ContractClause.contract_id == contract_id).all()
        if clauses:
            texts = [c.text_content for c in clauses]
            import openai
            client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            embeddings = []
            for i in range(0, len(texts), 100):
                chunk = texts[i:i+100]
                res = await client.embeddings.create(
                    model="text-embedding-3-small",
                    input=chunk
                )
                embeddings.extend([item.embedding for item in res.data])

            if len(embeddings) == len(clauses):
                for clause, emb in zip(clauses, embeddings):
                    clause.embedding = emb
                db.commit()
                print(f"Successfully generated and saved embeddings for {len(clauses)} clauses.")
            else:
                print(f"Warning: Count mismatch in embeddings generation: {len(embeddings)} vs {len(clauses)}")
    except Exception as emb_err:
        print(f"Failed to generate clause embeddings: {emb_err}")


async def _verify_contract_redlines(db, contract, contract_id: str, analysis_meta: dict):
    from .models import ContractClause
    existing = contract.metadata_json or {}
    parent_id = existing.get("parent_contract_id")
    if parent_id:
        # Fetch parent contract clauses
        parent_clauses = db.query(ContractClause).filter(ContractClause.contract_id == parent_id).all()

        if parent_clauses:
            # Update status callback to keep client informed
            existing["processing_step"] = "Verifying resolved redlines against parent version..."
            contract.metadata_json = existing
            db.commit()

            # Fetch current contract clauses
            new_clauses = db.query(ContractClause).filter(ContractClause.contract_id == contract_id).all()

            # Run redline verification
            use_llm = analysis_meta.get("analysis_mode") == "llm"
            try:
                from .agents import verify_previous_redlines
                redline_resolutions = await verify_previous_redlines(parent_clauses, new_clauses, use_llm=use_llm)
                existing = contract.metadata_json or {}
                existing["redline_resolutions"] = redline_resolutions
            except Exception as ve:
                print(f"Error during redline verification: {ve}")
                # Fallback using heuristic verifier manually
                try:
                    from .agents import _heuristic_verify_redline
                    resolutions = []
                    parent_risks = [c for c in parent_clauses if (c.risk_level.value if hasattr(c.risk_level, "value") else str(c.risk_level)) in {"HIGH", "CRITICAL"}]

                    nc_dict = {}
                    for nc in new_clauses:
                        nc_type_key = nc.clause_type.lower().strip()
                        if nc_type_key not in nc_dict:
                            nc_dict[nc_type_key] = nc

                    for pc in parent_risks:
                        pc_type_key = pc.clause_type.lower().strip()
                        matched_nc = nc_dict.get(pc_type_key)
                        if not matched_nc and new_clauses:
                            matched_nc = new_clauses[0]

                        new_text = matched_nc.text_content if matched_nc else ""
                        nc_id = str(matched_nc.id) if matched_nc else ""
                        status, new_risk_level, details = _heuristic_verify_redline(pc.text_content, pc.redline_suggestion or "", new_text)
                        resolutions.append({
                            "clause_type": pc.clause_type,
                            "parent_clause_id": str(pc.id),
                            "parent_text": pc.text_content,
                            "parent_risk_level": pc.risk_level.value if hasattr(pc.risk_level, "value") else str(pc.risk_level),
                            "parent_redline_suggestion": pc.redline_suggestion or "",
                            "new_clause_id": nc_id,
                            "new_text": new_text,
                            "new_risk_level": new_risk_level,
                            "status": status,
                            "verification_details": details
                        })
                    existing = contract.metadata_json or {}
                    existing["redline_resolutions"] = resolutions
                except Exception as he:
                    print(f"Deep fallback verification failed: {he}")


async def _extract_and_save_obligations(contract, raw_text: str):
    existing = contract.metadata_json or {}
    try:
        from .agents import extract_contract_obligations
        obligation_result = await extract_contract_obligations(raw_text)
        obligations_data = [
            {
                "title": o.title,
                "description": o.description,
                "party_responsible": o.party_responsible,
                "due_trigger": o.due_trigger,
                "category": o.category,
            }
            for o in obligation_result.obligations
        ]
        existing["obligations"] = obligations_data
    except Exception as oe:
        print(f"Obligation extraction failed (non-fatal): {oe}")
        existing["obligations"] = []


async def analyze_contract_background(contract_id: str, raw_text: str):
    print(f"Background task started for contract: {contract_id}")
    
    try:
        from .models import Contract, ContractStatus
        from .database import SessionLocal
        # Define callback to update detailed step
        async def update_status(step_msg: str):
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
        analysis_results, analysis_meta = await _run_analysis_pipeline(contract_id, raw_text, update_status)
        
        # 2. Save to DB (Postgres/pgvector)
        db = SessionLocal()
        try:
            save_analysis_results(db, contract_id, analysis_results)
            # Mark which analysis mode was used.
            contract = db.query(Contract).filter(Contract.id == contract_id).first()
            if contract:
                # Story: Generate embeddings for semantic search
                await _generate_clause_embeddings(db, contract, contract_id)
                
                # Check for parent and run redline verification
                await _verify_contract_redlines(db, contract, contract_id, analysis_meta)
                
                # Run obligation extraction
                await _extract_and_save_obligations(contract, raw_text)

                existing = contract.metadata_json or {}
                contract.metadata_json = {**existing, **analysis_meta}
                log_contract_event(db, contract_id, "analysis", "Analysis completed", analysis_meta)
                db.commit()
            print(f"Background task complete. Saved {len(analysis_results)} clauses.")
        finally:
            db.close()
            
    except Exception as e:
        print(f"Error in background task: {e}")
        from .models import Contract, ContractStatus
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
    parent_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Read bytes
    file_bytes = await file.read()
    
    # 2. Extract Text and Hash
    file_hash, raw_text = await extract_text_from_pdf(file_bytes)
    meta = extract_contract_metadata(raw_text)
    from datetime import datetime
    upload_date = datetime.utcnow().date().isoformat()
    std_name = standardized_filename(meta, upload_date)
    
    # Check if exists (specifically owned by current_user)
    existing_contract = None
    if not parent_id:
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
    parent_contract = None
    version_number = 1
    if parent_id:
        parent_contract = db.query(Contract).filter(Contract.id == parent_id, Contract.user_id == current_user.id).first()
        if parent_contract:
            parent_version = parent_contract.metadata_json.get("version_number", 1) if parent_contract.metadata_json else 1
            version_number = parent_version + 1
            
    metadata = {"raw_text": raw_text, **meta}
    if parent_id and parent_contract:
        metadata["parent_contract_id"] = parent_id
        metadata["version_number"] = version_number
    else:
        metadata["version_number"] = 1
        
    new_contract = Contract(
        filename=std_name,
        file_hash=file_hash,
        status=ContractStatus.PROCESSING,
        metadata_json=metadata,
        user_id=current_user.id
    )
    db.add(new_contract)
    db.flush()
    log_contract_event(db, str(new_contract.id), "ingest", "PDF uploaded for analysis", {"cache": "miss", "mode": "pdf"})
    db.commit()
    db.refresh(new_contract)
    
    # 4. Dispatch to background worker
    background_tasks.add_task(analyze_contract_background, str(new_contract.id), raw_text)
    
    return {
        "filename": new_contract.filename, 
        "contract_id": str(new_contract.id),
        "status": new_contract.status.value if hasattr(new_contract.status, "value") else str(new_contract.status),
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
        .limit(100)
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


@app.get("/api/v1/risks")
async def list_all_risks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetch all high and critical severity risk clauses across all completed contracts owned by the current user.
    """
    contracts = (
        db.query(Contract)
        .filter(Contract.user_id == current_user.id, Contract.status == ContractStatus.COMPLETED)
        .all()
    )
    contract_ids = [c.id for c in contracts]
    contract_map = {str(c.id): c for c in contracts}
    
    if not contract_ids:
        return {"risks": []}
        
    # Query clauses with HIGH or CRITICAL risk
    clauses = (
        db.query(ContractClause)
        .filter(
            ContractClause.contract_id.in_(contract_ids),
            ContractClause.risk_level.in_([RiskLevel.HIGH, RiskLevel.CRITICAL])
        )
        .all()
    )
    
    # Sort clauses: CRITICAL first, then HIGH
    severity_order = {"CRITICAL": 0, "HIGH": 1}
    clauses = sorted(
        clauses,
        key=lambda c: severity_order.get(c.risk_level.value if c.risk_level else "HIGH", 9)
    )
    
    result = []
    for c in clauses:
        contract_obj = contract_map.get(str(c.contract_id))
        if not contract_obj:
            continue
            
        # Resolve redline suggestion
        redline = c.redline_suggestion
        if not redline or not redline.strip():
            redline = _heuristic_redline(c.clause_type, c.text_content, c.risk_level.value if c.risk_level else "LOW")
            
        result.append({
            "id": str(c.id),
            "contract_id": str(c.contract_id),
            "contract_filename": contract_obj.filename,
            "clause_type": c.clause_type,
            "text_content": c.text_content,
            "risk_level": c.risk_level.value if c.risk_level else "LOW",
            "risk_reasoning": c.risk_reasoning,
            "redline_suggestion": redline,
            "created_at": contract_obj.created_at.isoformat()
        })
        
    return {"risks": result}


@app.get("/api/v1/contracts/{contract_id}")
async def get_contract(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
        
    overall_risk = "LOW"
    risk_counts = (contract.metadata_json or {}).get("risk_counts", {})
    if risk_counts.get("CRITICAL", 0) > 0:
        overall_risk = "CRITICAL"
    elif risk_counts.get("HIGH", 0) > 0:
        overall_risk = "HIGH"
    elif risk_counts.get("MEDIUM", 0) > 0:
        overall_risk = "MEDIUM"

    return {
        "contract": {
            "id": str(contract.id),
            "filename": contract.filename,
            "status": contract.status.value,
            "metadata_json": contract.metadata_json,
            "overall_risk": overall_risk if contract.status == ContractStatus.COMPLETED else None,
            "created_at": contract.created_at.isoformat()
        }
    }


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
    return {"signup_disabled": is_signup_disabled()}

@app.post("/api/v1/auth/signup")
async def signup(payload: UserSignupIn, db: Session = Depends(get_db)):
    if is_signup_disabled():
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


# ---------------------------------------------------------------------------
# Chat with Contract — RAG-powered Q&A using clause context
# ---------------------------------------------------------------------------

class ChatMessageIn(BaseModel):
    question: str
    history: list[dict] = []


class ChatSourceOut(BaseModel):
    clause_type: str
    text_excerpt: str
    risk_level: str


class ChatResponseOut(BaseModel):
    answer: str
    sources: list[ChatSourceOut]


class ReminderOut(BaseModel):
    id: str
    contract_id: str
    reminder_type: str
    status: str
    due_date: str
    title: str
    body: str | None = None
    letter: dict | None = None


class CreateReminderIn(BaseModel):
    reminder_type: str
    due_date: str
    title: str
    body: str | None = None


class TemplateCreateIn(BaseModel):
    name: str
    description: str | None = None
    raw_text: str


class TemplateCompareIn(BaseModel):
    template_id: str


class VendorEmailDraftIn(BaseModel):
    tone: str | None = "professional"
    include: str | None = "unresolved"  # unresolved | all

@app.post("/api/v1/contracts/{contract_id}/chat")
async def chat_with_contract(
    contract_id: str,
    payload: ChatMessageIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    RAG-powered chat: finds the most relevant clauses for the question
    and uses them as context for GPT-4.1 to answer.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract.status != ContractStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Contract analysis must be completed before chatting.")

    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    from .chat_service import generate_chat_response

    result = await generate_chat_response(
        contract=contract,
        question=question,
        history=payload.history,
        db=db,
    )

    sources = [ChatSourceOut(**s) for s in result["sources"]]
    return ChatResponseOut(answer=result["answer"], sources=sources)


# ---------------------------------------------------------------------------
# Calendar — contract expiry and renewal timeline
# ---------------------------------------------------------------------------

@app.get("/api/v1/calendar")
async def get_calendar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns all completed contracts with expiry/renewal date information,
    sorted by earliest upcoming date, with urgency classification.
    """
    from datetime import date

    contracts = (
        db.query(Contract)
        .filter(Contract.user_id == current_user.id)
        .order_by(Contract.created_at.desc())
        .all()
    )

    today = date.today()
    items = []

    for c in contracts:
        meta = c.metadata_json or {}
        expiry_date_str = meta.get("expiry_date")
        contract_date_str = meta.get("contract_date")
        renewal_notice_days = meta.get("renewal_notice_days")
        contract_term = meta.get("contract_term")

        # Compute days until expiry
        days_until_expiry = None
        expiry_date_parsed = None
        if expiry_date_str:
            try:
                expiry_date_parsed = date.fromisoformat(expiry_date_str)
                days_until_expiry = (expiry_date_parsed - today).days
            except Exception:
                pass

        # Compute urgency level
        if days_until_expiry is not None:
            if days_until_expiry < 0:
                urgency = "expired"
            elif days_until_expiry <= 30:
                urgency = "critical"
            elif days_until_expiry <= 60:
                urgency = "warning"
            elif days_until_expiry <= 90:
                urgency = "soon"
            else:
                urgency = "safe"
        else:
            urgency = "unknown"

        # Compute renewal deadline
        renewal_deadline_str = None
        if expiry_date_parsed and renewal_notice_days:
            from datetime import timedelta
            renewal_deadline = expiry_date_parsed - timedelta(days=renewal_notice_days)
            renewal_deadline_str = renewal_deadline.isoformat()

        # Derive overall risk
        risk_counts = meta.get("risk_counts", {})
        if risk_counts.get("CRITICAL", 0) > 0:
            overall_risk = "CRITICAL"
        elif risk_counts.get("HIGH", 0) > 0:
            overall_risk = "HIGH"
        elif risk_counts.get("MEDIUM", 0) > 0:
            overall_risk = "MEDIUM"
        else:
            overall_risk = "LOW"

        items.append({
            "id": str(c.id),
            "filename": c.filename,
            "status": c.status.value,
            "contract_type": meta.get("contract_type"),
            "company": meta.get("company"),
            "contract_date": contract_date_str,
            "expiry_date": expiry_date_str,
            "days_until_expiry": days_until_expiry,
            "renewal_notice_days": renewal_notice_days,
            "renewal_deadline": renewal_deadline_str,
            "contract_term": contract_term,
            "urgency": urgency,
            "overall_risk": overall_risk if c.status.value == "COMPLETED" else None,
            "created_at": c.created_at.isoformat(),
        })

    # Sort: expired first (ascending days), then upcoming (ascending), then unknown
    def sort_key(item):
        d = item["days_until_expiry"]
        if d is None:
            return (2, 0)
        if d < 0:
            return (0, d)  # expired, most recent first
        return (1, d)  # upcoming, soonest first

    items.sort(key=sort_key)

    # Fetch upcoming reminders (next 90 days) for bannering in the UI
    try:
        horizon = datetime.now(timezone.utc) + timedelta(days=90)
        reminders = (
            db.query(ContractReminder)
            .filter(ContractReminder.user_id == current_user.id, ContractReminder.status == "OPEN", ContractReminder.due_date <= horizon)
            .order_by(ContractReminder.due_date.asc())
            .limit(50)
            .all()
        )
        reminder_items = [
            {
                "id": str(r.id),
                "contract_id": str(r.contract_id),
                "reminder_type": str(r.reminder_type),
                "due_date": r.due_date.isoformat(),
                "title": r.title,
            }
            for r in reminders
        ]
    except Exception:
        reminder_items = []

    return {"items": items, "reminders": reminder_items}


# ---------------------------------------------------------------------------
# Vendors — group contracts by counterparty
# ---------------------------------------------------------------------------

@app.get("/api/v1/vendors")
async def get_vendors(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Groups all user contracts by vendor/counterparty name.
    Returns aggregated risk info per vendor.
    """
    contracts = (
        db.query(Contract)
        .filter(Contract.user_id == current_user.id)
        .order_by(Contract.created_at.desc())
        .all()
    )

    vendor_map: dict = {}
    severity = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}

    for c in contracts:
        meta = c.metadata_json or {}
        vendor_name = (meta.get("company") or "").strip() or "Unknown Vendor"

        risk_counts = meta.get("risk_counts", {})
        if risk_counts.get("CRITICAL", 0) > 0:
            overall_risk = "CRITICAL"
        elif risk_counts.get("HIGH", 0) > 0:
            overall_risk = "HIGH"
        elif risk_counts.get("MEDIUM", 0) > 0:
            overall_risk = "MEDIUM"
        else:
            overall_risk = "LOW"

        if vendor_name not in vendor_map:
            vendor_map[vendor_name] = {
                "name": vendor_name,
                "contracts": [],
                "worst_risk": "LOW",
                "total_critical": 0,
                "total_high": 0,
            }

        vendor_map[vendor_name]["contracts"].append({
            "id": str(c.id),
            "filename": c.filename,
            "status": c.status.value,
            "overall_risk": overall_risk if c.status.value == "COMPLETED" else None,
            "contract_type": meta.get("contract_type"),
            "expiry_date": meta.get("expiry_date"),
            "created_at": c.created_at.isoformat(),
        })

        vendor_map[vendor_name]["total_critical"] += risk_counts.get("CRITICAL", 0)
        vendor_map[vendor_name]["total_high"] += risk_counts.get("HIGH", 0)

        if severity.get(overall_risk, 0) > severity.get(vendor_map[vendor_name]["worst_risk"], 0):
            if c.status.value == "COMPLETED":
                vendor_map[vendor_name]["worst_risk"] = overall_risk

    # Sort vendors: most risky first, then by contract count
    vendors = list(vendor_map.values())
    vendors.sort(key=lambda v: (-severity.get(v["worst_risk"], 0), -len(v["contracts"])))

    return {"vendors": vendors}


# ---------------------------------------------------------------------------
# Clause repository search (cross-contract semantic search)
# ---------------------------------------------------------------------------

class ClauseSearchIn(BaseModel):
    query: str
    top_k: int = 12


@app.post("/api/v1/clauses/search")
async def clause_repository_search(
    payload: ClauseSearchIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (payload.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="query is required")
    top_k = max(1, min(int(payload.top_k or 12), 25))

    import openai
    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        emb = await client.embeddings.create(model="text-embedding-3-small", input=q)
        q_embedding = emb.data[0].embedding
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {str(e)}")

    try:
        rows = (
            db.query(ContractClause, Contract)
            .join(Contract, Contract.id == ContractClause.contract_id)
            .filter(Contract.user_id == current_user.id, ContractClause.embedding.isnot(None))
            .order_by(ContractClause.embedding.cosine_distance(q_embedding))
            .limit(top_k)
            .all()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vector search failed: {str(e)}")

    results = []
    analytics = {"by_clause_type": {}, "by_risk_level": {}}
    for clause, contract in rows:
        risk = clause.risk_level.value if clause.risk_level else "LOW"
        ctype = (clause.clause_type or "Unknown").strip()
        analytics["by_clause_type"][ctype] = analytics["by_clause_type"].get(ctype, 0) + 1
        analytics["by_risk_level"][risk] = analytics["by_risk_level"].get(risk, 0) + 1
        results.append(
            {
                "contract_id": str(contract.id),
                "contract_filename": contract.filename,
                "clause_id": str(clause.id),
                "clause_type": clause.clause_type,
                "risk_level": risk,
                "text_excerpt": (clause.text_content or "")[:420],
            }
        )

    return {"results": results, "analytics": analytics}


# ---------------------------------------------------------------------------
# Global assistant chat (bottom-left assistant)
# ---------------------------------------------------------------------------

class AssistantChatIn(BaseModel):
    question: str
    history: list[dict] = []


@app.post("/api/v1/assistant/chat")
async def assistant_chat(
    payload: AssistantChatIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")

    # Retrieve cross-contract clause context for grounding
    import openai
    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    try:
        emb = await client.embeddings.create(model="text-embedding-3-small", input=question)
        q_embedding = emb.data[0].embedding
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {str(e)}")

    matches = (
        db.query(ContractClause, Contract)
        .join(Contract, Contract.id == ContractClause.contract_id)
        .filter(Contract.user_id == current_user.id, ContractClause.embedding.isnot(None))
        .order_by(ContractClause.embedding.cosine_distance(q_embedding))
        .limit(6)
        .all()
    )

    context_parts = []
    sources = []
    for clause, contract in matches:
        risk = clause.risk_level.value if clause.risk_level else "LOW"
        context_parts.append(f"[{contract.filename} :: {clause.clause_type} | Risk: {risk}]\n{(clause.text_content or '')[:900]}")
        sources.append(
            {
                "contract_id": str(contract.id),
                "contract_filename": contract.filename,
                "clause_id": str(clause.id),
                "clause_type": clause.clause_type,
                "risk_level": risk,
                "text_excerpt": (clause.text_content or "")[:220],
            }
        )

    system_prompt = (
        "You are ContractsPulse Copilot for procurement managers. "
        "You help answer questions and find relevant clause examples across the user's contracts. "
        "Use ONLY the provided clause excerpts. If you lack context, ask a follow-up question or say you can't confirm. "
        "When you cite a clause, mention the contract filename."
    )
    history_messages = []
    for h in (payload.history or [])[-8:]:
        role = h.get("role", "user")
        content = h.get("content", "")
        if role in {"user", "assistant"} and content:
            history_messages.append({"role": role, "content": content})

    separator = "\n\n---\n\n"
    joined_context = separator.join(context_parts) if context_parts else "(none)"
    user_message = f"Relevant Clauses:\n{joined_context}\n\nQuestion: {question}"
    try:
        primary_model = _openai_assistant_model()
        try:
            resp = await client.chat.completions.create(
                model=primary_model,
                messages=[{"role": "system", "content": system_prompt}, *history_messages, {"role": "user", "content": user_message}],
                max_tokens=700,
                temperature=0.2,
            )
        except Exception:
            fallback_model = os.getenv("OPENAI_MODEL_ASSISTANT_FALLBACK", "gpt-4.1-mini").strip()
            resp = await client.chat.completions.create(
                model=fallback_model,
                messages=[{"role": "system", "content": system_prompt}, *history_messages, {"role": "user", "content": user_message}],
                max_tokens=700,
                temperature=0.2,
            )
        answer = resp.choices[0].message.content or ""
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assistant chat failed: {str(e)}")

    return {"answer": answer, "sources": sources}


# ---------------------------------------------------------------------------
# Contract template library + comparison
# ---------------------------------------------------------------------------

@app.get("/api/v1/templates")
async def list_templates(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(ContractTemplate)
        .filter(ContractTemplate.user_id == current_user.id)
        .order_by(ContractTemplate.created_at.desc())
        .all()
    )
    return {
        "templates": [
            {
                "id": str(t.id),
                "name": t.name,
                "description": t.description,
                "created_at": t.created_at.isoformat(),
            }
            for t in rows
        ]
    }


@app.post("/api/v1/templates")
async def create_template(
    payload: TemplateCreateIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    name = (payload.name or "").strip()
    raw_text = (payload.raw_text or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not raw_text:
        raise HTTPException(status_code=400, detail="raw_text is required")

    t = ContractTemplate(
        user_id=current_user.id,
        name=name,
        description=(payload.description or "").strip() or None,
        raw_text=raw_text,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": str(t.id)}


@app.post("/api/v1/contracts/{contract_id}/compare-template")
async def compare_contract_to_template(
    contract_id: str,
    payload: TemplateCompareIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    template = (
        db.query(ContractTemplate)
        .filter(ContractTemplate.id == payload.template_id, ContractTemplate.user_id == current_user.id)
        .first()
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    clauses = db.query(ContractClause).filter(ContractClause.contract_id == contract_id).all()
    clauses_with_embeddings = [c for c in clauses if getattr(c, "embedding", None) is not None]

    # Chunk template into paragraphs for lightweight coverage check
    paras = [p.strip() for p in re.split(r"\n{2,}", template.raw_text) if p.strip()]
    paras = paras[:30]

    import openai
    import numpy as np
    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    if not clauses_with_embeddings or not paras:
        return {
            "template_id": str(template.id),
            "template_name": template.name,
            "summary": "Insufficient embeddings or template text for semantic comparison.",
            "missing_sections": [],
            "nonstandard_sections": [],
        }

    # Embed template paragraphs
    try:
        emb = await client.embeddings.create(model="text-embedding-3-small", input=paras)
        para_embeddings = [d.embedding for d in emb.data]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding failed: {str(e)}")

    missing_sections = []

    # Pre-calculate distances in memory to avoid N+1 DB queries
    # We already have clauses_with_embeddings fetched earlier at the start of the endpoint.

    # Pre-normalize clause embeddings outside the loop to optimize
    normalized_clauses = []
    for clause in clauses_with_embeddings:
        ce_np = np.array(clause.embedding)
        norm = np.linalg.norm(ce_np)
        if norm > 0:
            ce_np = ce_np / norm
        normalized_clauses.append((clause, ce_np))

    for i, (para, pe) in enumerate(zip(paras, para_embeddings)):
        # Find the closest clause in memory
        nearest_clause = None
        min_dist = float("inf")

        pe_np = np.array(pe)
        norm = np.linalg.norm(pe_np)
        if norm > 0:
            pe_np = pe_np / norm

        for clause, ce_np in normalized_clauses:
            # np.dot(pe_np, ce_np) gets the cosine similarity because both are normalized
            dist = 1.0 - np.dot(pe_np, ce_np)
            if dist < min_dist:
                min_dist = dist
                nearest_clause = clause

        if not nearest_clause:
            missing_sections.append({"index": i, "template_excerpt": para[:260]})
            continue

        # Use a conservative heuristic:
        # if clause type doesn't overlap with the para keywords, treat as potentially missing.
        key = " ".join(re.findall(r"[A-Za-z]{5,}", para.lower())[:12])
        if key and key not in ((nearest_clause.text_content or "").lower()):
            missing_sections.append({"index": i, "template_excerpt": para[:260], "nearest_clause_type": nearest_clause.clause_type})

    # Clause position sanity: compare ordering of top similar template paras vs clause index order
    # (This is intentionally lightweight; UI can evolve later.)
    nonstandard_sections = []
    if len(paras) >= 6:
        nonstandard_sections.append(
            {
                "note": "Position analysis is a v1 heuristic; focus on missing sections first.",
            }
        )

    return {
        "template_id": str(template.id),
        "template_name": template.name,
        "missing_sections": missing_sections[:12],
        "nonstandard_sections": nonstandard_sections,
    }


# ---------------------------------------------------------------------------
# Obligations — get or generate obligations for a contract
# ---------------------------------------------------------------------------

@app.get("/api/v1/contracts/{contract_id}/obligations")
async def get_obligations(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Return stored obligations for a contract."""
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    obligations = (contract.metadata_json or {}).get("obligations", None)
    return {
        "obligations": obligations,  # None = not yet generated; [] = generated but empty
        "generated": obligations is not None,
    }


# ---------------------------------------------------------------------------
# Renewal/notice automation — reminders + letter generation
# ---------------------------------------------------------------------------

def _parse_iso_date(dt_str: str):
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def _generate_renewal_notice_letter(contract: Contract) -> dict:
    meta = contract.metadata_json or {}
    vendor = meta.get("company") or "Counterparty"
    expiry_date = meta.get("expiry_date") or ""
    renewal_notice_days = meta.get("renewal_notice_days") or ""
    filename = contract.filename

    subject = f"Notice of Non-Renewal / Opt-Out — {filename}"
    body = (
        f"To: {vendor}\n"
        f"Re: {filename}\n\n"
        f"This letter provides written notice that we elect not to renew / to opt out of any automatic renewal under the Agreement.\n\n"
        f"Please confirm in writing that the Agreement will terminate at the end of the current term. "
        f"Our records indicate an expiry/term end date of {expiry_date} and a notice period of {renewal_notice_days} days (if applicable).\n\n"
        f"Sincerely,\n"
        f"[Your Name]\n"
        f"[Title]\n"
        f"[Company]\n"
    )
    return {"subject": subject, "body": body}


def _format_redline_items_for_email(resolutions: list[dict], include: str) -> tuple[str, list[dict]]:
    include = (include or "unresolved").lower().strip()
    if include not in {"unresolved", "all"}:
        include = "unresolved"

    def is_included(r: dict) -> bool:
        if include == "all":
            return True
        return (r.get("status") or "").upper() in {"UNRESOLVED", "PARTIALLY_RESOLVED"}

    items = [r for r in (resolutions or []) if is_included(r)]
    bullets = []
    for r in items:
        clause_type = r.get("clause_type") or "Clause"
        status = (r.get("status") or "UNRESOLVED").replace("_", " ").title()
        originally = (r.get("parent_risk_level") or "").title()
        proposed = (r.get("parent_redline_suggestion") or "").strip()
        bullets.append(
            {
                "clause_type": clause_type,
                "status": status,
                "original_risk_level": originally,
                "proposed_redline": proposed[:900],
            }
        )
    lines = []
    for b in bullets:
        lines.append(f"- {b['clause_type']} (status: {b['status']}; originally {b['original_risk_level']})")
        if b.get("proposed_redline"):
            lines.append(f"  Suggested language: {b['proposed_redline']}")
    text = "\n".join(lines) or "- (none)"
    return text, bullets


def _format_proposed_redlines_for_email(clauses: list, include: str) -> tuple[str, list[dict]]:
    """Build email bullets from a contract's own proposed redlines.

    Used for first-version contracts (no counterparty edits to verify yet), so the
    vendor email requests the AI-recommended redlines directly from the clause analysis.
    include='unresolved' -> only HIGH/CRITICAL clauses; include='all' -> any clause with a redline.
    """
    include = (include or "unresolved").lower().strip()
    if include not in {"unresolved", "all"}:
        include = "unresolved"

    severity = {"CRITICAL": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
    bullets = []
    for c in (clauses or []):
        risk = c.risk_level.value if hasattr(c.risk_level, "value") else (str(c.risk_level) if c.risk_level else "LOW")
        redline = (c.redline_suggestion or "").strip()
        if not redline and risk in {"HIGH", "CRITICAL"}:
            redline = (_heuristic_redline(c.clause_type, c.text_content, risk) or "").strip()
        if not redline:
            continue
        if include == "unresolved" and risk not in {"HIGH", "CRITICAL"}:
            continue
        bullets.append(
            {
                "clause_type": c.clause_type or "Clause",
                "status": "Proposed",
                "original_risk_level": risk.title(),
                "proposed_redline": redline[:900],
            }
        )

    bullets.sort(key=lambda b: severity.get((b["original_risk_level"] or "").upper(), 0), reverse=True)
    lines = []
    for b in bullets:
        lines.append(f"- {b['clause_type']} (risk: {b['original_risk_level']})")
        if b.get("proposed_redline"):
            lines.append(f"  Suggested language: {b['proposed_redline']}")
    text = "\n".join(lines) or "- (none)"
    return text, bullets


@app.post("/api/v1/contracts/{contract_id}/redlines/email")
async def generate_vendor_redlines_email(
    contract_id: str,
    payload: VendorEmailDraftIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate (but do not send) an email draft to the vendor summarizing proposed redlines
    and requested changes based on redline verification results.
    """
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    meta = contract.metadata_json or {}
    vendor = (meta.get("company") or "Vendor").strip()
    resolutions = meta.get("redline_resolutions") or []
    if not isinstance(resolutions, list):
        resolutions = []

    include = (payload.include or "unresolved").lower().strip()
    if resolutions:
        bullets_text, bullets = _format_redline_items_for_email(resolutions, include=include)
    else:
        # First-version contract (no counterparty edits yet): request our proposed redlines.
        clauses = db.query(ContractClause).filter(ContractClause.contract_id == contract_id).all()
        bullets_text, bullets = _format_proposed_redlines_for_email(clauses, include=include)

    import openai
    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    system_prompt = (
        "You are an experienced procurement professional writing a concise email to a vendor. "
        "Your goal is to clearly request specific contract edits (redlines) without being adversarial. "
        "For each item you are given the clause and the specific suggested language we want — incorporate that "
        "actual language so the vendor knows exactly what change is being requested. Be concrete, not generic. "
        "Do not claim legal conclusions. Do not invent contract terms beyond what is provided. "
        "Do NOT include a signature block: no placeholder name (e.g. '[Your Name]'), job title, company name, or "
        "contact details. End with a simple closing such as 'Best regards,' on its own line. "
        "Output ONLY JSON with keys: subject, body."
    )

    tone = (payload.tone or "professional").strip().lower()
    filename = contract.filename
    version_num = (meta.get("version_number") or "")
    subject_hint = f"Redlines / Requested Revisions — {filename}"

    user_prompt = (
        f"Vendor: {vendor}\n"
        f"Contract: {filename}\n"
        f"Contract Version: {version_num}\n"
        f"Include: {include}\n"
        f"Tone: {tone}\n\n"
        f"Requested items (each may include the specific suggested language to request):\n{bullets_text}\n\n"
        "Write an email that:\n"
        "- Opens with brief appreciation and context\n"
        "- For each item, names the clause and states the specific change we're requesting, referencing the suggested language provided above\n"
        "- Asks for confirmation and a timeline\n"
        "- Mentions we can hop on a quick call if helpful\n"
        "- Ends with a simple closing only (e.g. 'Best regards,'); do NOT add a name, job title, or company\n"
        f"Subject should be similar to: {subject_hint}\n"
    )

    try:
        try:
            resp = await client.chat.completions.create(
                model=_openai_chat_model(),
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                max_tokens=550,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
        except Exception:
            resp = await client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL_CHAT_FALLBACK", "gpt-4.1").strip(),
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                max_tokens=550,
                temperature=0.2,
                response_format={"type": "json_object"},
            )
        content = resp.choices[0].message.content or "{}"
        import json
        draft = json.loads(content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email generation failed: {str(e)}")

    subject = (draft.get("subject") or subject_hint).strip()
    body = (draft.get("body") or "").strip()
    if not body:
        body = (
            f"Hi {vendor},\n\n"
            f"Sharing a few requested edits for {filename}:\n{bullets_text}\n\n"
            "Thanks,\n"
        )

    return {
        "email": {"subject": subject, "body": body},
        "items": bullets,
        "generated_by_ai": True,
    }


@app.get("/api/v1/contracts/{contract_id}/reminders")
async def list_contract_reminders(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    rows = (
        db.query(ContractReminder)
        .filter(ContractReminder.contract_id == contract_id, ContractReminder.user_id == current_user.id)
        .order_by(ContractReminder.due_date.asc())
        .all()
    )
    return {
        "reminders": [
            ReminderOut(
                id=str(r.id),
                contract_id=str(r.contract_id),
                reminder_type=str(r.reminder_type),
                status=str(r.status),
                due_date=r.due_date.isoformat(),
                title=r.title,
                body=r.body,
                letter=r.letter_json or None,
            ).model_dump()
            for r in rows
        ]
    }


@app.post("/api/v1/contracts/{contract_id}/reminders")
async def create_contract_reminder(
    contract_id: str,
    payload: CreateReminderIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    due_dt = _parse_iso_date(payload.due_date)
    if not due_dt:
        raise HTTPException(status_code=400, detail="Invalid due_date; expected ISO datetime")

    reminder = ContractReminder(
        user_id=current_user.id,
        contract_id=contract.id,
        reminder_type=payload.reminder_type,
        status="OPEN",
        due_date=due_dt,
        title=(payload.title or "").strip() or "Reminder",
        body=(payload.body or "").strip() or None,
        letter_json={},
    )
    db.add(reminder)
    db.commit()
    db.refresh(reminder)

    return {"id": str(reminder.id)}


@app.post("/api/v1/contracts/{contract_id}/letters/renewal-notice")
async def generate_renewal_notice_letter(
    contract_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    letter = _generate_renewal_notice_letter(contract)
    return {"letter": letter}


@app.post("/api/v1/contracts/{contract_id}/obligations/generate")
async def generate_obligations_on_demand(
    contract_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Generate obligations on-demand for contracts that were analyzed before this feature."""
    contract = db.query(Contract).filter(Contract.id == contract_id, Contract.user_id == current_user.id).first()
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    if contract.status != ContractStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Contract must be completed to generate obligations.")

    raw_text = (contract.metadata_json or {}).get("raw_text", "")
    if not raw_text:
        raise HTTPException(status_code=400, detail="Raw text not available for this contract.")

    async def _generate(cid: str, text: str):
        from .database import SessionLocal
        db2 = SessionLocal()
        try:
            result = await extract_contract_obligations(text)
            obligations_data = [
                {
                    "title": o.title,
                    "description": o.description,
                    "party_responsible": o.party_responsible,
                    "due_trigger": o.due_trigger,
                    "category": o.category,
                }
                for o in result.obligations
            ]
            c = db2.query(Contract).filter(Contract.id == cid).first()
            if c:
                existing = c.metadata_json or {}
                existing["obligations"] = obligations_data
                c.metadata_json = existing
                db2.commit()
        except Exception as e:
            print(f"On-demand obligation generation failed: {e}")
        finally:
            db2.close()

    background_tasks.add_task(_generate, contract_id, raw_text)
    return {"message": "Obligation generation started.", "status": "generating"}
