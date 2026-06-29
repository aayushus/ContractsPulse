from backend.app.agents import _heuristic_risk

def test_heuristic_risk_critical():
    """Test that two critical keywords result in CRITICAL risk (score >= 6)."""
    clause = "We will hold harmless and provide uncapped liability."
    result = _heuristic_risk("General", clause)
    assert result.risk_level == "CRITICAL"
    assert "multiple high-liability keywords detected" in result.risk_reasoning
    assert result.indemnification_risk == 1.0
    assert result.liability_risk == 1.0

def test_heuristic_risk_high():
    """Test that two high risk keywords result in HIGH risk (score >= 3)."""
    clause = "You may terminate for convenience but must provide a warranty."
    result = _heuristic_risk("Termination", clause)
    assert result.risk_level == "HIGH"
    assert "elevated-risk clause keywords detected" in result.risk_reasoning
    assert result.termination_risk == 1.0

def test_heuristic_risk_medium():
    """Test that a medium risk keyword results in MEDIUM risk (score >= 1)."""
    clause = "Please submit the invoice for payment."
    result = _heuristic_risk("Payment", clause)
    assert result.risk_level == "MEDIUM"
    assert "standard commercial risk keywords detected" in result.risk_reasoning
    assert result.payment_risk == 1.0

def test_heuristic_risk_low():
    """Test that no matching keywords results in LOW risk."""
    clause = "This is a standard generic clause with nothing risky."
    result = _heuristic_risk("General", clause)
    assert result.risk_level == "LOW"
    assert "no obvious high-risk keywords detected" in result.risk_reasoning

def test_heuristic_risk_auto_renewal_exception():
    """Test that an auto-renewal keyword bumps a LOW risk to MEDIUM."""
    clause = "The contract will auto-renew next year."
    result = _heuristic_risk("Renewal", clause)
    # auto-renew doesn't add to score, so score=0. But has_auto_renewal=True bumps to MEDIUM
    assert result.risk_level == "MEDIUM"
    assert "auto-renewal clause detected" in result.risk_reasoning

def test_heuristic_risk_empty_input():
    """Test handling of empty string."""
    result = _heuristic_risk("General", "")
    assert result.risk_level == "LOW"
    assert "no obvious high-risk keywords detected" in result.risk_reasoning

def test_heuristic_risk_none_input():
    """Test handling of None input."""
    result = _heuristic_risk("General", None)
    assert result.risk_level == "LOW"
    assert "no obvious high-risk keywords detected" in result.risk_reasoning

def test_heuristic_risk_dimensions():
    """Test that specific dimension scores are correctly set based on keywords."""
    clause = "governing law venue confidential intellectual property payment"
    result = _heuristic_risk("General", clause)
    assert result.dispute_risk == 1.0
    assert result.confidentiality_risk == 1.0
    assert result.ip_risk == 1.0
    assert result.payment_risk == 1.0
    assert result.termination_risk == 0.0

def test_heuristic_risk_redline():
    """Test that a redline suggestion is generated for CRITICAL risk."""
    clause = "uncapped unlimited liability"
    result = _heuristic_risk("Limitation of Liability", clause)
    assert result.risk_level == "CRITICAL"
    assert result.redline_suggestion is not None
    assert "Limitation of Liability" in result.redline_suggestion
