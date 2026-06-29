import os
from unittest.mock import patch, MagicMock

import httpx
from typer.testing import CliRunner

# Import the CLI app
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from contractpulse import app, API_BASE

runner = CliRunner()

def test_feedback_success():
    with patch("httpx.post") as mock_post:
        # Mock successful response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = runner.invoke(app, ["feedback", "job_123", "clause_456", "--is-risky", "--note", "Test note"])

        assert result.exit_code == 0
        mock_post.assert_called_once_with(
            f"{API_BASE}/api/v1/feedback/job_123/clause_456",
            json={"is_risky": True, "note": "Test note"},
            timeout=15,
        )

def test_feedback_not_risky_success():
    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        result = runner.invoke(app, ["feedback", "job_123", "clause_456", "--not-risky", "--note", "Test note"])

        assert result.exit_code == 0
        mock_post.assert_called_once_with(
            f"{API_BASE}/api/v1/feedback/job_123/clause_456",
            json={"is_risky": False, "note": "Test note"},
            timeout=15,
        )

def test_feedback_missing_flags():
    result = runner.invoke(app, ["feedback", "job_123", "clause_456"])
    assert result.exit_code == 1
    assert "Specify either --not-risky or --is-risky" in result.stdout

def test_feedback_mutually_exclusive_flags():
    result = runner.invoke(app, ["feedback", "job_123", "clause_456", "--is-risky", "--not-risky"])
    assert result.exit_code == 1
    assert "--not-risky and --is-risky are mutually exclusive" in result.stdout

def test_feedback_http_status_error():
    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {"detail": "Feedback not found"}
        mock_exc = httpx.HTTPStatusError("404 Client Error", request=MagicMock(), response=mock_response)

        # We need mock_post to return a response that will raise the error when raise_for_status is called
        mock_resp_obj = MagicMock()
        mock_resp_obj.raise_for_status.side_effect = mock_exc
        mock_post.return_value = mock_resp_obj

        result = runner.invoke(app, ["feedback", "job_123", "clause_456", "--is-risky"])

        assert result.exit_code == 1
        assert "Error:" in result.stdout
        assert "Feedback not found" in result.stdout

def test_feedback_http_error():
    with patch("httpx.post") as mock_post:
        mock_post.side_effect = httpx.HTTPError("Connection timeout")

        result = runner.invoke(app, ["feedback", "job_123", "clause_456", "--is-risky"])

        assert result.exit_code == 1
        assert "Request failed:" in result.stdout
        assert "Connection timeout" in result.stdout
