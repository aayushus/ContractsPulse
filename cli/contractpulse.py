#!/usr/bin/env python3
"""
ContractsPulse CLI
Usage:
  contractpulse analyze --file <path>
  contractpulse report  <job_id> [--output pdf] [--save <path>]
  contractpulse feedback <job_id> <clause_id> (--not-risky | --is-risky) [--note <text>]
"""
import os
import sys
import time
from pathlib import Path
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich import print as rprint

app = typer.Typer(
    name="contractpulse",
    help="ContractsPulse — legal-grade contract risk analysis from the command line.",
    add_completion=False,
)
console = Console()

API_BASE = os.getenv("CONTRACTSPULSE_API_URL", "http://localhost:8000").rstrip("/")

RISK_COLORS = {
    "CRITICAL": "bold red",
    "HIGH": "bold yellow",
    "MEDIUM": "yellow",
    "LOW": "green",
}

RISK_ICONS = {
    "CRITICAL": "🔴",
    "HIGH": "🟠",
    "MEDIUM": "🟡",
    "LOW": "🟢",
}


# ---------------------------------------------------------------------------
# analyze
# ---------------------------------------------------------------------------

@app.command()
def analyze(
    file: Path = typer.Option(..., "--file", "-f", help="Path to the contract PDF to analyze."),
):
    """
    Upload a contract PDF, wait for analysis, and display the risk report.

    Story 011: overall risk score and one-line summary appear first, before any clause detail.
    Story 009: broad IP assignment clauses are flagged with a plain-English side-project warning.
    Story 010: each flagged clause shows a professional redline and a plain-English rationale.
    """
    if not file.exists():
        console.print(f"[red]File not found:[/] {file}")
        raise typer.Exit(1)

    # 1. Upload
    with console.status("[bold cyan]Uploading contract…[/]"):
        with open(file, "rb") as fh:
            try:
                r = httpx.post(
                    f"{API_BASE}/api/v1/contracts/upload",
                    files={"file": (file.name, fh, "application/pdf")},
                    timeout=60,
                )
                r.raise_for_status()
            except httpx.HTTPError as exc:
                console.print(f"[red]Upload failed:[/] {exc}")
                raise typer.Exit(1)

    data = r.json()
    job_id = data["contract_id"]
    console.print(f"[dim]Job ID:[/] [bold]{job_id}[/]")

    # 2. Poll until complete
    _poll_until_complete(job_id)

    # 3. Fetch structured report and render
    _render_report(job_id)


def _poll_until_complete(job_id: str) -> None:
    """Poll /status until COMPLETED or FAILED, showing a live progress bar."""
    with console.status("[bold cyan]Analyzing…[/]", spinner="dots") as status:
        while True:
            try:
                r = httpx.get(f"{API_BASE}/api/v1/contracts/{job_id}/status", timeout=15)
                r.raise_for_status()
            except httpx.HTTPError:
                time.sleep(3)
                continue

            st = r.json()
            job_status = st.get("status", "")
            step = st.get("processing_step") or ""
            progress = st.get("progress")
            eta = st.get("eta_seconds")

            eta_str = f"  ETA ~{eta}s" if eta is not None else ""
            progress_str = ""
            if progress:
                cur = progress.get("current", 0)
                total = progress.get("total", 0)
                progress_str = f"  [{cur}/{total}]"

            status.update(f"[bold cyan]{step or 'Analyzing…'}[/]{progress_str}{eta_str}")

            if job_status == "COMPLETED":
                break
            if job_status == "FAILED":
                console.print("[red]Analysis failed.[/]")
                raise typer.Exit(1)

            time.sleep(2)


def _render_report(job_id: str, *, show_all_medium: bool = False) -> dict:
    """Fetch /report, render to terminal, return raw report dict."""
    try:
        r = httpx.get(f"{API_BASE}/api/v1/contracts/{job_id}/report", timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        console.print(f"[red]Failed to fetch report:[/] {exc}")
        raise typer.Exit(1)

    report = r.json()
    overall = report.get("overall_risk", "LOW")
    risk_counts = report.get("risk_counts", {})
    summary = report.get("summary", "")
    flagged = report.get("flagged_clauses", [])

    # ── Header: risk score first (Story 011) ──────────────────────────────────
    color = RISK_COLORS.get(overall, "white")
    icon = RISK_ICONS.get(overall, "")

    counts_parts = []
    for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW"):
        n = risk_counts.get(level, 0)
        if n:
            counts_parts.append(f"[{RISK_COLORS[level]}]{n} {level}[/]")
    counts_line = "  ·  ".join(counts_parts)

    console.print()
    console.print(Panel(
        f"[{color}]{icon}  Risk Score: {overall}[/]\n\n"
        f"{counts_line}\n\n"
        f"[italic]{summary}[/italic]",
        title="[bold]ContractsPulse Report[/]",
        expand=False,
    ))

    if not flagged:
        console.print("\n[green]No HIGH or CRITICAL clauses found.[/]")
        return report

    # ── Flagged clauses (Story 010: redline + rationale) ───────────────────
    console.print()
    console.rule("[bold]Flagged Clauses  (HIGH + CRITICAL)[/]")

    for clause in flagged:
        risk = clause.get("risk_level", "HIGH")
        color = RISK_COLORS.get(risk, "white")
        icon = RISK_ICONS.get(risk, "")

        console.print()
        console.print(f"[{color}]{icon}  [{risk}]  {clause.get('clause_type', 'Clause')}[/]")
        console.print(f"[dim]Clause ID: {clause.get('id', '')}[/]")

        reasoning = clause.get("risk_reasoning") or ""
        if reasoning:
            console.print(f"\n  [bold]Why it matters:[/] {reasoning}")

        redline = clause.get("redline_suggestion") or ""
        if redline:
            console.print(f"\n  [bold]Suggested redline:[/]")
            # Indent each line of the redline for readability
            for line in redline.strip().splitlines():
                console.print(f"    [italic]{line}[/]")

        excerpt = clause.get("text_excerpt", "")
        if excerpt:
            console.print(f"\n  [dim]Contract text (excerpt):[/]")
            for line in excerpt[:400].strip().splitlines():
                console.print(f"    [dim]{line}[/]")

        console.print()

    return report


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------

@app.command()
def report(
    job_id: str = typer.Argument(..., help="Job ID (contract_id) from a previous analyze run."),
    output: str = typer.Option("terminal", "--output", "-o", help="Output format: 'terminal' or 'pdf'."),
    save: Optional[Path] = typer.Option(None, "--save", "-s", help="Path to save the PDF (required when --output pdf)."),
):
    """
    Display or export the report for a previously analyzed contract.

    Story 012: --output pdf --save <path> generates a PDF for legal reviewers containing
    only the overall score, flagged clauses with plain-English explanations, and redlines.
    """
    if output == "pdf":
        if save is None:
            console.print("[red]--save <path> is required when using --output pdf[/]")
            raise typer.Exit(1)
        _export_pdf(job_id, save)
    else:
        _render_report(job_id)


def _export_pdf(job_id: str, dest: Path) -> None:
    """Story 012: generate a PDF report from the structured JSON report."""
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Table as RLTable, TableStyle
        )
    except ImportError:
        console.print("[red]reportlab is required for PDF export.[/]")
        console.print("  Install it: pip install reportlab")
        raise typer.Exit(1)

    try:
        r = httpx.get(f"{API_BASE}/api/v1/contracts/{job_id}/report", timeout=15)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        console.print(f"[red]Failed to fetch report:[/] {exc}")
        raise typer.Exit(1)

    data = r.json()
    overall = data.get("overall_risk", "LOW")
    risk_counts = data.get("risk_counts", {})
    summary = data.get("summary", "")
    filename = data.get("filename", job_id)
    flagged = data.get("flagged_clauses", [])

    RISK_PDF_COLORS = {
        "CRITICAL": colors.HexColor("#c0392b"),
        "HIGH": colors.HexColor("#e67e22"),
        "MEDIUM": colors.HexColor("#f1c40f"),
        "LOW": colors.HexColor("#27ae60"),
    }

    doc = SimpleDocTemplate(
        str(dest),
        pagesize=LETTER,
        leftMargin=inch,
        rightMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )
    styles = getSampleStyleSheet()
    story = []

    # Header
    title_style = ParagraphStyle("cp_title", parent=styles["Title"], fontSize=20, spaceAfter=6)
    story.append(Paragraph("ContractsPulse — Legal Review Request", title_style))
    story.append(Paragraph(f"<font size='10' color='#555555'>Contract: {filename}</font>", styles["Normal"]))
    story.append(Spacer(1, 0.15 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))
    story.append(Spacer(1, 0.15 * inch))

    # Overall risk score
    risk_color = RISK_PDF_COLORS.get(overall, colors.black)
    score_style = ParagraphStyle("cp_score", parent=styles["Heading1"], fontSize=16, textColor=risk_color)
    story.append(Paragraph(f"Overall Risk Score: {overall}", score_style))

    counts_parts = "  ·  ".join(
        f"{risk_counts.get(lv, 0)} {lv}" for lv in ("CRITICAL", "HIGH", "MEDIUM", "LOW") if risk_counts.get(lv, 0)
    )
    story.append(Paragraph(counts_parts, styles["Normal"]))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"<i>{summary}</i>", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cccccc")))

    if not flagged:
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph("No HIGH or CRITICAL clauses detected.", styles["Normal"]))
    else:
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph("Flagged Clauses for Legal Review", styles["Heading2"]))
        story.append(Spacer(1, 0.1 * inch))

        for clause in flagged:
            risk = clause.get("risk_level", "HIGH")
            rc = RISK_PDF_COLORS.get(risk, colors.black)
            clause_type = clause.get("clause_type", "Clause")

            heading_style = ParagraphStyle(
                "cp_clause_heading",
                parent=styles["Heading3"],
                textColor=rc,
                spaceAfter=4,
            )
            story.append(Paragraph(f"[{risk}]  {clause_type}", heading_style))
            story.append(Paragraph(f"<font size='8' color='#888888'>Clause ID: {clause.get('id', '')}</font>", styles["Normal"]))

            reasoning = clause.get("risk_reasoning") or ""
            if reasoning:
                label_style = ParagraphStyle("cp_label", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10)
                story.append(Spacer(1, 0.05 * inch))
                story.append(Paragraph("Why it matters:", label_style))
                story.append(Paragraph(reasoning, styles["Normal"]))

            redline = clause.get("redline_suggestion") or ""
            if redline:
                story.append(Spacer(1, 0.08 * inch))
                label_style = ParagraphStyle("cp_label2", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10)
                story.append(Paragraph("Suggested Redline:", label_style))
                redline_style = ParagraphStyle(
                    "cp_redline",
                    parent=styles["Normal"],
                    leftIndent=12,
                    fontName="Courier",
                    fontSize=9,
                    textColor=colors.HexColor("#1a5276"),
                    backColor=colors.HexColor("#eaf4fb"),
                    borderPad=4,
                )
                story.append(Paragraph(redline.replace("\n", "<br/>"), redline_style))

            excerpt = clause.get("text_excerpt", "")
            if excerpt:
                story.append(Spacer(1, 0.08 * inch))
                label_style = ParagraphStyle("cp_label3", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=10)
                story.append(Paragraph("Contract Text (excerpt):", label_style))
                excerpt_style = ParagraphStyle(
                    "cp_excerpt",
                    parent=styles["Normal"],
                    leftIndent=12,
                    fontSize=8,
                    textColor=colors.HexColor("#555555"),
                )
                story.append(Paragraph(excerpt[:600].replace("\n", "<br/>"), excerpt_style))

            story.append(Spacer(1, 0.2 * inch))
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#dddddd")))
            story.append(Spacer(1, 0.1 * inch))

    # Footer note
    story.append(Spacer(1, 0.3 * inch))
    footer_style = ParagraphStyle("cp_footer", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#888888"))
    story.append(Paragraph(
        "Generated by ContractsPulse. This report highlights clauses for legal review and does not constitute legal advice.",
        footer_style,
    ))

    doc.build(story)
    console.print(f"[green]PDF saved:[/] {dest}")


# ---------------------------------------------------------------------------
# feedback
# ---------------------------------------------------------------------------

@app.command()
def feedback(
    job_id: str = typer.Argument(..., help="Job ID (contract_id)."),
    clause_id: str = typer.Argument(..., help="Clause ID to correct."),
    not_risky: bool = typer.Option(False, "--not-risky", help="Mark this clause as NOT risky (false positive)."),
    is_risky: bool = typer.Option(False, "--is-risky", help="Mark this clause as risky (missed risk)."),
    note: Optional[str] = typer.Option(None, "--note", "-n", help="Optional explanation for the correction."),
):
    """
    Correct a risk score. Stories 013 & 014.

    Examples:
      contractpulse feedback job_a1b2c3d4 clause_008 --not-risky --note "Standard in SaaS MSAs"
      contractpulse feedback job_a1b2c3d4 clause_012 --is-risky  --note "Unlimited audit access is a security risk"
    """
    if not not_risky and not is_risky:
        console.print("[red]Specify either --not-risky or --is-risky[/]")
        raise typer.Exit(1)
    if not_risky and is_risky:
        console.print("[red]--not-risky and --is-risky are mutually exclusive[/]")
        raise typer.Exit(1)

    risky = is_risky

    try:
        r = httpx.post(
            f"{API_BASE}/api/v1/feedback/{job_id}/{clause_id}",
            json={"is_risky": risky, "note": note},
            timeout=15,
        )
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.json().get("detail", str(exc))
        console.print(f"[red]Error:[/] {detail}")
        raise typer.Exit(1)
    except httpx.HTTPError as exc:
        console.print(f"[red]Request failed:[/] {exc}")
        raise typer.Exit(1)

    data = r.json()
    console.print(f"[green]✓[/] {data.get('message', 'Feedback recorded.')}  [dim](ID: {data.get('feedback_id', '')})[/]")


if __name__ == "__main__":
    app()
