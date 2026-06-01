import pytest
from app.main import _compute_overall_risk

def test_compute_overall_risk_empty():
    assert _compute_overall_risk({}) == "LOW"

def test_compute_overall_risk_only_low():
    assert _compute_overall_risk({"LOW": 5}) == "LOW"

def test_compute_overall_risk_medium():
    assert _compute_overall_risk({"LOW": 2, "MEDIUM": 1}) == "MEDIUM"

def test_compute_overall_risk_high():
    assert _compute_overall_risk({"LOW": 2, "MEDIUM": 5, "HIGH": 1}) == "HIGH"

def test_compute_overall_risk_critical():
    assert _compute_overall_risk({"LOW": 2, "MEDIUM": 5, "HIGH": 1, "CRITICAL": 1}) == "CRITICAL"

def test_compute_overall_risk_zeros():
    # Zeros shouldn't trigger the higher risk levels
    assert _compute_overall_risk({"CRITICAL": 0, "HIGH": 0, "MEDIUM": 1, "LOW": 5}) == "MEDIUM"
    assert _compute_overall_risk({"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 5}) == "LOW"
