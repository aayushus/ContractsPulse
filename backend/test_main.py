import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import _compute_overall_risk, app, is_signup_disabled, extract_auto_renewal_info

client = TestClient(app)

def test_extract_auto_renewal_info_empty():
    assert extract_auto_renewal_info(None) is None
    assert extract_auto_renewal_info("") is None

def test_extract_auto_renewal_info_no_keyword():
    text = "This contract is for a duration of one year. No renewal info."
    assert extract_auto_renewal_info(text) is None

def test_extract_auto_renewal_info_with_keyword_no_days():
    text = "This contract will auto-renew for another term."
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": None}

    text = "The renewal term begins immediately."
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": None}

    text = "It will automatically renew unless cancelled."
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": None}

def test_extract_auto_renewal_info_with_keyword_and_days():
    text = "This contract will auto-renew. You must cancel 30 days prior to the end."
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": 30}

    text = "Automatically renews unless written notice is given 60 days before expiration."
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": 60}

    text = "The renewal term applies if not cancelled 90 days prior to renewal."
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": 90}

    text = "auto renewal if not cancelled 14 days before."
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": 14}

def test_extract_auto_renewal_info_case_insensitivity():
    text = "AUTO RENEW unless notice 45 DAYS BEFORE"
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": 45}

    text = "Automatically Renew with 15 days prior to"
    assert extract_auto_renewal_info(text) == {"opt_out_days_before_renewal": 15}

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
