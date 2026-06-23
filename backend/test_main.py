import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import _compute_overall_risk, app, is_signup_disabled

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "ContractsPulse API is running"}

def test_health_check_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

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

def test_is_signup_disabled_default():
    with patch.dict(os.environ, {}, clear=True):
        assert is_signup_disabled() is False

def test_is_signup_disabled_truthy():
    for val in ["true", "1", "yes", " TRUE ", "Yes", " 1 "]:
        with patch.dict(os.environ, {"DISABLE_SIGNUP": val}, clear=True):
            assert is_signup_disabled() is True

def test_is_signup_disabled_falsy():
    for val in ["false", "0", "no", " FALSE ", "No", " 0 ", "random"]:
        with patch.dict(os.environ, {"DISABLE_SIGNUP": val}, clear=True):
            assert is_signup_disabled() is False
