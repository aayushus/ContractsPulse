import os
from pydantic import BaseModel, Field
from typing import List
from pydantic_ai import Agent
import re

# ---------------------------------------------------------
# Pydantic Schemas for Structured Output
# ---------------------------------------------------------

class ExtractedClause(BaseModel):
    clause_type: str = Field(description="The category of the clause. e.g., 'Indemnification', 'Termination', 'Payment Terms'")
    text_content: str = Field(description="The exact raw text of the clause extracted from the document.")

class ContractExtractionResult(BaseModel):
    clauses: List[ExtractedClause] = Field(description="A comprehensive list of all critical legal clauses found in the document.")

class RiskAnalysisResult(BaseModel):
    risk_level: str = Field(description="Must be exactly one of: LOW, MEDIUM, HIGH, CRITICAL")
    risk_reasoning: str = Field(description="A concise explanation of why this risk level was chosen based on standard legal risk tolerances. For HIGH/CRITICAL, this must be ONE sentence and act as a copy/paste-ready negotiation rationale.")
    redline_suggestion: str | None = Field(default=None, description="If risk is HIGH or CRITICAL, provide suggested replacement legal text that is fair and market-standard.")
    # Story 007: per-dimension technical breakdown (0..1). Use 0 if not applicable.
    termination_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk of termination terms being unfavorable to the signer.")
    payment_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk of payment/fees being unfavorable or ambiguous.")
    liability_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk due to liability caps/exclusions/damages.")
    indemnification_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk due to indemnity/defense obligations.")
    ip_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk related to IP ownership, assignment, or licensing.")
    confidentiality_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk related to confidentiality obligations and carveouts.")
    dispute_risk: float = Field(default=0.0, ge=0.0, le=1.0, description="Risk related to governing law, venue, arbitration, or dispute procedures.")
    confidence: float = Field(default=0.6, ge=0.0, le=1.0, description="Model confidence in the assigned risk level and scoring (0..1).")
    # Enriched by the app (not the LLM) at runtime.
    debug_json: dict = Field(default_factory=dict, description="Technical debug metadata (model id, latency, composite score).")

# ---------------------------------------------------------
# The Agents
# ---------------------------------------------------------

# Agent 1: The Extractor
# Responsible for taking unstructured text and breaking it into logical clauses.
extractor_agent = Agent(
    os.getenv("OPENAI_MODEL_EXTRACTOR", "openai:gpt-4.1-mini"),
    output_type=ContractExtractionResult,
    retries=3,
    system_prompt=(
        "You are an expert legal AI assistant. Your task is to analyze the provided raw contract text "
        "and segment it into distinct, logical clauses. Ensure no critical text is missed. "
        "Categorize each clause accurately."
    )
)

# Agent 2: The Risk Assessor
# Responsible for evaluating a single clause for potential liabilities.
risk_agent = Agent(
    os.getenv("OPENAI_MODEL_RISK", "openai:gpt-4.1"),
    output_type=RiskAnalysisResult,
    retries=3,
    system_prompt=(
        "You are a Senior Legal Counsel. Analyze the provided legal clause and assess its risk level "
        "from the perspective of the party signing the contract. "
        "Look for hidden liabilities, uncapped indemnifications, unusual termination clauses, or aggressive payment terms. "
        "IMPORTANT — IP Assignment clauses: if the clause assigns ownership of 'all work', 'all deliverables', or "
        "'anything created during the engagement/term', treat this as HIGH risk and explain in plain English that "
        "'this means the client owns anything you create while under this contract — including side projects and "
        "personal tools'. The redline must narrow scope to work created specifically for deliverables under the agreement. "
        "Provide a concrete reasoning for your assigned risk level. "
        "If the risk level is HIGH or CRITICAL: "
        "(1) provide ONE sentence of rationale in risk_reasoning that explains why the suggested change protects the signer "
        "— write it in plain English so a non-lawyer can use it verbatim to explain the change to their client, "
        "(2) provide a market-standard suggested replacement in redline_suggestion written in clean professional legal "
        "language (not casual) that is scoped narrowly enough that a reasonable counterparty would accept it. "
        "Also provide 0..1 scores for each of these dimensions: termination_risk, payment_risk, liability_risk, "
        "indemnification_risk, ip_risk, confidentiality_risk, dispute_risk, and provide a confidence score (0..1). "
        "Use 0 for dimensions that are not applicable to this clause."
    )
)

# Agent 3: The Redline Verifier
# Responsible for comparing original clause, suggested redline, and counterparty's updated language.
class RedlineVerification(BaseModel):
    status: str = Field(description="Must be exactly: RESOLVED, PARTIALLY_RESOLVED, or UNRESOLVED")
    new_risk_level: str = Field(description="Must be exactly one of: LOW, MEDIUM, HIGH, CRITICAL")
    verification_details: str = Field(description="A concise plain-English explanation of why this status was chosen. Be specific about what was changed or what risks remain.")

redline_verifier_agent = Agent(
    os.getenv("OPENAI_MODEL_RISK", "openai:gpt-4.1"),
    output_type=RedlineVerification,
    retries=3,
    system_prompt=(
        "You are a Senior Legal Counsel specializing in contract negotiations and redline validation. "
        "Your task is to compare the original (parent) contract clause text, the suggested redline recommendation, "
        "and the new (child) updated contract clause text. "
        "Analyze whether the counterparty successfully resolved the original legal concern and "
        "implemented the spirit of the redline suggestion. "
        "Assign a status (RESOLVED, PARTIALLY_RESOLVED, or UNRESOLVED), evaluate the new risk level "
        "(LOW, MEDIUM, HIGH, or CRITICAL), and provide clear, professional explanation details about "
        "the changes made or remaining liabilities. Speak directly, and be extremely objective."
    )
)

# Agent 4: The Obligation Extractor
# Extracts actionable procurement obligations from the full contract text.
class ObligationItem(BaseModel):
    title: str = Field(description="Short, action-oriented title. e.g. 'Submit Monthly Invoice', 'Provide 30-Day Termination Notice'")
    description: str = Field(description="Concise description of the obligation in plain English.")
    party_responsible: str = Field(description="Which party must fulfill this: 'Vendor', 'Customer', 'Both', or 'Either'")
    due_trigger: str = Field(description="When is this due? e.g. 'Net 30 after invoice', 'Upon contract expiry', '30 days before renewal', 'Monthly', 'Upon delivery'")
    category: str = Field(description="One of: payment, delivery, notice, reporting, compliance, renewal, confidentiality, other")

class ObligationExtractionResult(BaseModel):
    obligations: List[ObligationItem] = Field(description="All actionable obligations extracted from the contract. Focus on concrete, time-bound, or triggered duties.")

obligation_agent = Agent(
    os.getenv("OPENAI_MODEL_EXTRACTOR", "openai:gpt-4.1-mini"),
    output_type=ObligationExtractionResult,
    retries=2,
    system_prompt=(
        "You are an expert procurement manager and legal analyst. "
        "Extract all actionable obligations from the provided contract text. "
        "Focus on concrete duties that require action: payment deadlines, delivery requirements, "
        "notice obligations, reporting requirements, renewal deadlines, and compliance obligations. "
        "For each obligation, identify WHO must do WHAT, and WHEN (triggered by what event or date). "
        "Skip vague or aspirational language. Only extract obligations with a clear responsible party and trigger. "
        "Limit to the 15 most important and actionable obligations."
    )
)

async def extract_contract_obligations(raw_text: str) -> ObligationExtractionResult:
    """Run the obligation extractor on the full contract text."""
    try:
        run = await obligation_agent.run(raw_text[:12000])  # bound context
        return run.output
    except Exception as e:
        print(f"Obligation extraction failed: {e}")
        return ObligationExtractionResult(obligations=[])


# ---------------------------------------------------------
# Orchestration Example
# ---------------------------------------------------------


async def process_contract_text(raw_text: str, update_status_callback=None):
    """
    Orchestrates the agent workflow: Extract -> Assess -> Save (pseudo-code for saving)
    """
    if update_status_callback:
        await update_status_callback("Segmenting document into logical clauses...")
    print("Starting Extraction Phase...")
    # 1. Run Extraction
    try:
        extraction_run = await extractor_agent.run(raw_text)
        extracted_clauses: ContractExtractionResult = extraction_run.output
    except Exception as e:
        print(f"FAILED during extraction with error: {str(e)}")
        import traceback
        traceback.print_exc()
        if update_status_callback:
            await update_status_callback(f"Failed during extraction: {str(e)}")
        raise e
    
    print(f"Extracted {len(extracted_clauses.clauses)} clauses. Moving to Risk Analysis...")
    
    analyzed_clauses = []
    
    # 2. Run Risk Analysis (This can be parallelized in production)
    total_clauses = len(extracted_clauses.clauses)
    for i, clause in enumerate(extracted_clauses.clauses):
        if update_status_callback:
            await update_status_callback(f"Analyzing risk: Clause {i+1} of {total_clauses}...")
            
        # We pass the clause text to the risk agent
        import time
        t0 = time.perf_counter()
        risk_run = await risk_agent.run(f"Clause Type: {clause.clause_type}\nText: {clause.text_content}")
        latency_ms = int((time.perf_counter() - t0) * 1000)
        risk_result: RiskAnalysisResult = risk_run.output

        dims = {
            "termination_risk": float(risk_result.termination_risk or 0.0),
            "payment_risk": float(risk_result.payment_risk or 0.0),
            "liability_risk": float(risk_result.liability_risk or 0.0),
            "indemnification_risk": float(risk_result.indemnification_risk or 0.0),
            "ip_risk": float(risk_result.ip_risk or 0.0),
            "confidentiality_risk": float(risk_result.confidentiality_risk or 0.0),
            "dispute_risk": float(risk_result.dispute_risk or 0.0),
        }
        composite = max(dims.values()) if dims else 0.0
        risk_result.debug_json = {
            "model": os.getenv("OPENAI_MODEL_RISK", "openai:gpt-4.1"),
            "latency_ms": latency_ms,
            "dimensions": dims,
            "composite_score": round(composite, 4),
            "confidence": float(risk_result.confidence or 0.0),
        }
        
        analyzed_clauses.append({
            "clause": clause,
            "analysis": risk_result
        })
        
        print(f"Analyzed {clause.clause_type} -> Risk: {risk_result.risk_level}")
        
    if update_status_callback:
        await update_status_callback("Saving results to database...")
        
    return analyzed_clauses


def _heuristic_segment_clauses(raw_text: str) -> List[ExtractedClause]:
    """
    Deterministic fallback segmenter used when the LLM is unavailable/hanging.
    Tries to split on numbered headings and common clause headings.
    """
    text = (raw_text or "").strip()
    if not text:
        return []

    # Normalize whitespace a bit for splitting.
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)

    # Split on numbered section headers like "1. DUTIES." or "12) TERM".
    # Hyphen must be first/last in a character class (or escaped) to avoid range parsing.
    parts = re.split(r"\n(?=(?:\d+\.|\d+\))\s*[A-Z][A-Z /\-]{2,80})", text)
    chunks: List[str] = []
    for p in parts:
        s = p.strip()
        if len(s) < 80:
            continue
        chunks.append(s)

    # If the split didn't work (some PDFs flatten headings), fall back to coarse chunks.
    if not chunks:
        para_parts = re.split(r"\n{2,}", text)
        chunks = [p.strip() for p in para_parts if len(p.strip()) >= 120]

    clauses: List[ExtractedClause] = []
    for c in chunks[:60]:  # bound work; this is a fallback
        first_line = c.split("\n", 1)[0].strip()
        # Best-effort clause type from the heading.
        m = re.match(r"^(?:\d+\.|\d+\))\s*([A-Z][A-Z /\-]{2,80})", first_line)
        clause_type = (m.group(1).strip().title() if m else "General")
        clauses.append(ExtractedClause(clause_type=clause_type, text_content=c[:4000]))
    return clauses


def _first_sentence(text: str) -> str:
    """
    Best-effort single-sentence extraction for UI copy/paste.
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Normalize whitespace and trim.
    t = re.sub(r"\s+", " ", t).strip()
    # Prefer splitting on sentence boundaries.
    m = re.search(r"([.!?])\s", t)
    if m:
        end = m.end(1)
        return t[:end].strip()
    # Fallback: clamp.
    return t[:220].rstrip(" ,;:-") + ("" if len(t) <= 220 else ".")


def _heuristic_redline(clause_type: str, clause_text: str, risk_level: str) -> str | None:
    """
    Deterministic redline suggestions for common risky clause patterns.
    Only used for HIGH/CRITICAL (or when LLM omitted the suggestion).
    """
    t = (clause_text or "").lower()
    ct = (clause_type or "").lower()

    # Auto-renewal: ensure explicit opt-out window + no silent renewal.
    if any(k in t for k in ["auto-renew", "auto renewal", "automatic renewal", "automatically renew"]):
        return (
            "Auto-Renewal. The Agreement will renew for successive one (1) year terms only if Customer "
            "provides written confirmation of renewal. Customer may elect not to renew by providing written notice "
            "at least thirty (30) days prior to the end of the then-current term. No fees will be due for any renewal "
            "term unless expressly agreed in writing by Customer."
        )

    # Limitation of liability / damages
    if "limitation of liability" in ct or "limit" in ct or any(k in t for k in ["limitation of liability", "consequential", "indirect", "punitive"]):
        return (
            "Limitation of Liability. Except for a party’s indemnification obligations, breach of confidentiality, "
            "or infringement of the other party’s intellectual property rights, each party’s aggregate liability "
            "arising out of or relating to this Agreement will not exceed the fees paid or payable by Customer to Vendor "
            "under this Agreement in the twelve (12) months preceding the event giving rise to the claim. In no event will "
            "either party be liable for any indirect, incidental, special, consequential, or punitive damages."
        )

    # Indemnification
    if "indemn" in ct or "hold harmless" in t or "indemnif" in t:
        return (
            "Indemnification. Each party will indemnify, defend, and hold harmless the other party from and against "
            "any third-party claims, damages, and reasonable costs (including attorneys’ fees) arising from the indemnifying "
            "party’s (a) gross negligence or willful misconduct, or (b) breach of this Agreement. Indemnification obligations "
            "will be subject to reasonable notice, control of the defense, and cooperation requirements."
        )

    # IP ownership / assignment — scope to deliverables only (Story 009)
    if any(k in t for k in ["intellectual property", "ip", "work product", "assignment", "assigns"]):
        return (
            "Intellectual Property. Customer will own all work product and deliverables specifically created for "
            "Customer pursuant to this Agreement upon receipt of full payment. For the avoidance of doubt, this "
            "assignment excludes: (a) Vendor’s pre-existing intellectual property, tools, frameworks, libraries, "
            "and general know-how; (b) any work created by Vendor outside the scope of this Agreement or not "
            "specifically commissioned hereunder, including any side projects, personal tools, or independently "
            "developed software; and (c) any open-source components subject to their respective licenses. Vendor "
            "is granted a limited, non-exclusive, royalty-free license to use Customer materials solely to perform "
            "the Services during the term of this Agreement."
        )

    # Termination for convenience / early termination
    if "terminate for convenience" in t or "termination" in ct:
        return (
            "Termination. Customer may terminate this Agreement for convenience upon thirty (30) days’ prior written notice. "
            "Upon termination, Customer will pay only for Services performed through the effective termination date, and Vendor "
            "will promptly refund any prepaid fees for Services not performed."
        )

    # General safety-net fallback when we have HIGH/CRITICAL but no recognized pattern.
    if risk_level in {"HIGH", "CRITICAL"}:
        return (
            "Proposed Revision. The parties will modify this clause to be mutual, commercially reasonable, and limited in scope, "
            "including appropriate caps on liability, clear notice/cure periods, and exclusions for indirect damages, consistent "
            "with market-standard terms for agreements of this type."
        )
    return None


def _heuristic_risk(clause_type: str, clause_text: str) -> RiskAnalysisResult:
    t = (clause_text or "").lower()

    has_auto_renewal = any(
        k in t
        for k in [
            "auto-renew",
            "auto renewal",
            "automatically renew",
            "automatic renewal",
            "renewal term",
            "non-renewal",
        ]
    )

    # Very rough keyword scoring. Goal is "not empty" and "directionally useful" when LLM is down.
    critical = [
        "unlimited liability",
        "uncapped",
        "without limitation",
        "indemnif",
        "hold harmless",
        "consequential",
        "punitive",
        "liquidated damages",
    ]
    high = [
        "terminate for convenience",
        "automatic renewal",
        "audit",
        "assignment",
        "governing law",
        "warranty",
        "confidential",
        "ip ownership",
    ]
    medium = [
        "payment",
        "invoice",
        "net ",
        "interest",
        "late fee",
        "insurance",
        "subcontract",
    ]

    score = 0
    score += 3 * sum(1 for k in critical if k in t)
    score += 2 * sum(1 for k in high if k in t)
    score += 1 * sum(1 for k in medium if k in t)

    if score >= 6:
        level = "CRITICAL"
        reasoning = "Heuristic: multiple high-liability keywords detected (e.g., indemnity/uncapped liability)."
    elif score >= 3:
        level = "HIGH"
        reasoning = "Heuristic: elevated-risk clause keywords detected (e.g., termination/assignment/warranty)."
    elif score >= 1:
        level = "MEDIUM"
        reasoning = "Heuristic: standard commercial risk keywords detected (e.g., payment/insurance)."
    else:
        level = "LOW"
        reasoning = "Heuristic: no obvious high-risk keywords detected."

    # Per product requirements, auto-renewal should never be silently LOW.
    if has_auto_renewal and level == "LOW":
        level = "MEDIUM"
        reasoning = "Heuristic: auto-renewal clause detected; confirm opt-out deadline to avoid unwanted renewals."

    redline = _heuristic_redline(clause_type, clause_text, level) if level in {"HIGH", "CRITICAL"} else None
    # Keep fallback rationale copy-friendly for HIGH/CRITICAL.
    if level in {"HIGH", "CRITICAL"}:
        reasoning = _first_sentence(
            reasoning
            if reasoning and reasoning.endswith(".")
            else (reasoning + ".")
        )

    # Dimension scores: coarse mapping from detected keywords.
    dims = {
        "termination_risk": 1.0 if "terminat" in t else 0.0,
        "payment_risk": 1.0 if any(k in t for k in ["payment", "invoice", "late fee", "interest"]) else 0.0,
        "liability_risk": 1.0 if any(k in t for k in ["limitation of liability", "consequential", "punitive", "without limitation", "uncapped"]) else 0.0,
        "indemnification_risk": 1.0 if "indemn" in t or "hold harmless" in t else 0.0,
        "ip_risk": 1.0 if any(k in t for k in ["intellectual property", "ip", "work product", "assignment"]) else 0.0,
        "confidentiality_risk": 1.0 if "confidential" in t else 0.0,
        "dispute_risk": 1.0 if any(k in t for k in ["governing law", "venue", "arbitration", "jurisdiction"]) else 0.0,
    }
    composite = max(dims.values()) if dims else 0.0

    rr = RiskAnalysisResult(
        risk_level=level,
        risk_reasoning=reasoning,
        redline_suggestion=redline,
        termination_risk=dims["termination_risk"],
        payment_risk=dims["payment_risk"],
        liability_risk=dims["liability_risk"],
        indemnification_risk=dims["indemnification_risk"],
        ip_risk=dims["ip_risk"],
        confidentiality_risk=dims["confidentiality_risk"],
        dispute_risk=dims["dispute_risk"],
        confidence=0.35,
    )
    rr.debug_json = {
        "model": "heuristic_fallback",
        "latency_ms": 0,
        "dimensions": dims,
        "composite_score": round(composite, 4),
        "confidence": 0.35,
    }
    return rr


def _enrich_ip_clause(
    clause_type: str,
    clause_text: str,
    risk_level: str,
    reasoning: str,
    redline: str | None,
) -> tuple[str, str, str | None]:
    """
    Story 009: For IP assignment clauses with broad scope ('all work during engagement'),
    ensure risk is HIGH, reasoning warns about side projects in plain English, and redline
    is scoped to deliverables only.
    """
    t = (clause_text or "").lower()
    ct = (clause_type or "").lower()

    is_ip = (
        any(k in ct for k in ["ip", "intellectual property", "work product", "assignment"])
        or any(k in t for k in ["intellectual property", "work product", "ip assignment", "assigns all"])
    )
    if not is_ip:
        return risk_level, reasoning, redline

    broad_scope = any(k in t for k in [
        "all work", "all deliverables", "during the engagement", "during the term",
        "engagement period", "created during", "developed during", "arising from",
        "any work", "all intellectual property", "solely and exclusively",
    ])
    if not broad_scope:
        return risk_level, reasoning, redline

    if risk_level not in {"HIGH", "CRITICAL"}:
        risk_level = "HIGH"

    reasoning = (
        "This means the client owns anything you create while under this contract "
        "— including side projects and personal tools."
    )
    if not (redline or "").strip():
        redline = _heuristic_redline(clause_type, clause_text, risk_level)

    return risk_level, reasoning, redline


async def process_contract_text_fallback(raw_text: str, update_status_callback=None):
    """
    Fallback pipeline that does not call external LLM providers.
    """
    if update_status_callback:
        await update_status_callback("LLM unavailable. Running heuristic extraction + risk scoring...")

    extracted = _heuristic_segment_clauses(raw_text)
    analyzed = []
    total = len(extracted)
    for i, clause in enumerate(extracted):
        if update_status_callback and i % 5 == 0:
            await update_status_callback(f"Heuristic analysis: Clause {i+1} of {total}...")
        analyzed.append({"clause": clause, "analysis": _heuristic_risk(clause.clause_type, clause.text_content)})

    if update_status_callback:
        await update_status_callback("Saving results to database...")
    return analyzed


async def verify_previous_redlines(parent_clauses: list, new_clauses: list, use_llm: bool = True) -> list:
    """
    Compares parent contract clauses that had HIGH or CRITICAL risk with the new contract clauses
    to verify if the recommended redlines were successfully resolved.
    """
    resolutions = []
    
    # We only care about high/critical risks in the parent contract
    parent_risks = [c for c in parent_clauses if (c.risk_level.value if hasattr(c.risk_level, "value") else str(c.risk_level)) in {"HIGH", "CRITICAL"}]
    
    # Create a dictionary for O(1) lookup of new clauses by clause_type
    nc_dict = {}
    for nc in new_clauses:
        nc_type = nc.clause_type if hasattr(nc, "clause_type") else (nc.get("clause") if isinstance(nc, dict) else nc).clause_type
        nc_type_key = nc_type.lower().strip()
        if nc_type_key not in nc_dict:
            nc_dict[nc_type_key] = nc

    for pc in parent_risks:
        # Find matching new clause of same type (case-insensitive)
        pc_type_key = pc.clause_type.lower().strip()
        matched_nc = nc_dict.get(pc_type_key)
                
        # If no exact match, skip or take a best-effort candidate
        if not matched_nc and new_clauses:
            matched_nc = new_clauses[0]
            
        if matched_nc:
            # Handle if matched_nc is dict (like analyzed_clauses result) or SQL Alchemy object
            if isinstance(matched_nc, dict):
                nc_clause = matched_nc.get("clause")
                new_text = nc_clause.text_content if nc_clause else ""
                nc_id = ""
            else:
                new_text = matched_nc.text_content
                nc_id = str(matched_nc.id) if hasattr(matched_nc, "id") else ""
                
            parent_text = pc.text_content
            parent_redline = pc.redline_suggestion or ""
            
            if use_llm and parent_redline.strip():
                try:
                    prompt = (
                        f"Clause Type: {pc.clause_type}\n\n"
                        f"Original Text (Parent):\n{parent_text}\n\n"
                        f"Suggested Redline:\n{parent_redline}\n\n"
                        f"New Text (Child):\n{new_text}"
                    )
                    run_result = await redline_verifier_agent.run(prompt)
                    verification: RedlineVerification = run_result.output
                    
                    status = verification.status.upper().strip()
                    new_risk_level = verification.new_risk_level.upper().strip()
                    details = verification.verification_details
                except Exception as e:
                    print(f"Failed to verify redline via LLM: {e}")
                    status, new_risk_level, details = _heuristic_verify_redline(parent_text, parent_redline, new_text)
            else:
                status, new_risk_level, details = _heuristic_verify_redline(parent_text, parent_redline, new_text)
                
            resolutions.append({
                "clause_type": pc.clause_type,
                "parent_clause_id": str(pc.id),
                "parent_text": parent_text,
                "parent_risk_level": pc.risk_level.value if hasattr(pc.risk_level, "value") else str(pc.risk_level),
                "parent_redline_suggestion": parent_redline,
                "new_clause_id": nc_id,
                "new_text": new_text,
                "new_risk_level": new_risk_level,
                "status": status,
                "verification_details": details
            })
            
    return resolutions

def _heuristic_verify_redline(parent_text: str, parent_redline: str, new_text: str) -> tuple[str, str, str]:
    """
    Deterministic fallback to compare texts if LLM is unavailable or disabled.
    """
    p_text = (parent_text or "").strip().lower()
    r_text = (parent_redline or "").strip().lower()
    n_text = (new_text or "").strip().lower()
    
    if not r_text:
        return "UNRESOLVED", "HIGH", "No redline recommendation was available to verify against."
        
    # Standard text similarity: if the new text is identical to parent text, it is unresolved
    if p_text == n_text:
        return "UNRESOLVED", "HIGH", "The updated clause text is completely identical to the original clause text. No changes were made."
        
    # Check if a key phrase from the redline is present in the new text
    words = [w for w in r_text.split() if len(w) > 4]
    matched_words = sum(1 for w in words if w in n_text)
    match_ratio = matched_words / len(words) if words else 0.0
    
    if match_ratio > 0.6 or r_text in n_text:
        return "RESOLVED", "LOW", "The new text incorporates key provisions from the recommended redline language, limiting potential exposure."
    elif match_ratio > 0.2:
        return "PARTIALLY_RESOLVED", "MEDIUM", "The clause was modified from its original state, but did not fully incorporate the recommended protective redline language."
    else:
        return "UNRESOLVED", "HIGH", "The clause was modified but did not adopt any of the protective terms recommended in the redline suggestion."

