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
    os.getenv("OPENAI_MODEL_EXTRACTOR", "openai-chat:gpt-4.1-mini"),
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
    os.getenv("OPENAI_MODEL_RISK", "openai-chat:gpt-4.1"),
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
            "model": os.getenv("OPENAI_MODEL_RISK", "openai-chat:gpt-4.1"),
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
