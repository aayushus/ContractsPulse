import sys
import os
import uuid
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app, get_current_user
from backend.app.database import get_db
from backend.app.models import User, Contract, ContractClause

client = TestClient(app)

@pytest.fixture
def mock_user():
    return User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        hashed_password="hashed_password"
    )

@pytest.fixture
def override_deps(mock_user):
    def _override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = _override_get_current_user

    yield

    app.dependency_overrides.clear()

def test_contract_not_found(override_deps):
    mock_db = MagicMock()
    # Mock return None for the contract query
    mock_db.query.return_value.filter.return_value.first.return_value = None

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    response = client.post(
        f"/api/v1/contracts/{uuid.uuid4()}/redlines/email",
        json={"tone": "professional", "include": "unresolved"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Contract not found"

def test_happy_path_with_resolutions(override_deps, mock_user):
    mock_db = MagicMock()

    # Setup mock contract with redline_resolutions
    contract_id = str(uuid.uuid4())
    mock_contract = Contract(
        id=contract_id,
        user_id=mock_user.id,
        filename="test_contract.pdf",
        metadata_json={
            "company": "Test Vendor",
            "version_number": "1.0",
            "redline_resolutions": [
                {
                    "status": "UNRESOLVED",
                    "clause_type": "Payment",
                    "parent_risk_level": "HIGH",
                    "parent_redline_suggestion": "Change payment terms to 30 days."
                }
            ]
        }
    )
    mock_db.query.return_value.filter.return_value.first.return_value = mock_contract

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    # Patch OpenAI
    mock_openai_response = MagicMock()
    mock_openai_response.choices = [
        MagicMock(message=MagicMock(content='{"subject": "Requested Revisions", "body": "Please update payment terms."}'))
    ]

    mock_create = AsyncMock(return_value=mock_openai_response)

    with patch("openai.AsyncOpenAI") as mock_openai_class:
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create = mock_create
        mock_openai_class.return_value = mock_openai_instance

        response = client.post(
            f"/api/v1/contracts/{contract_id}/redlines/email",
            json={"tone": "professional", "include": "unresolved"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"]["subject"] == "Requested Revisions"
        assert data["email"]["body"] == "Please update payment terms."
        assert len(data["items"]) == 1
        assert data["items"][0]["clause_type"] == "Payment"
        assert data["generated_by_ai"] is True

        mock_create.assert_called_once()

def test_happy_path_first_version_contract(override_deps, mock_user):
    mock_db = MagicMock()

    # Setup mock contract without redline_resolutions
    contract_id = str(uuid.uuid4())
    mock_contract = Contract(
        id=contract_id,
        user_id=mock_user.id,
        filename="test_contract.pdf",
        metadata_json={
            "company": "Test Vendor"
        }
    )

    # Setup ContractClause for fallback
    mock_clause = ContractClause(
        id=str(uuid.uuid4()),
        contract_id=contract_id,
        clause_type="Liability",
        risk_level="CRITICAL",
        redline_suggestion="Limit liability to 1M."
    )

    # Configure mock_db.query to return different things based on the model
    def mock_query(model):
        query_mock = MagicMock()
        if model == Contract:
            query_mock.filter.return_value.first.return_value = mock_contract
        elif model == ContractClause:
            query_mock.filter.return_value.all.return_value = [mock_clause]
        return query_mock

    mock_db.query.side_effect = mock_query

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    # Patch OpenAI
    mock_openai_response = MagicMock()
    mock_openai_response.choices = [
        MagicMock(message=MagicMock(content='{"subject": "Initial Redlines", "body": "See attached redlines."}'))
    ]

    mock_create = AsyncMock(return_value=mock_openai_response)

    with patch("openai.AsyncOpenAI") as mock_openai_class:
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create = mock_create
        mock_openai_class.return_value = mock_openai_instance

        response = client.post(
            f"/api/v1/contracts/{contract_id}/redlines/email",
            json={"tone": "firm", "include": "all"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"]["subject"] == "Initial Redlines"
        assert data["email"]["body"] == "See attached redlines."
        assert len(data["items"]) == 1
        assert data["items"][0]["clause_type"] == "Liability"
        assert data["generated_by_ai"] is True

        mock_create.assert_called_once()

def test_openai_fallback(override_deps, mock_user):
    mock_db = MagicMock()

    contract_id = str(uuid.uuid4())
    mock_contract = Contract(
        id=contract_id,
        user_id=mock_user.id,
        filename="test_contract.pdf",
        metadata_json={"company": "Test Vendor", "redline_resolutions": []}
    )

    def mock_query(model):
        query_mock = MagicMock()
        if model == Contract:
            query_mock.filter.return_value.first.return_value = mock_contract
        elif model == ContractClause:
            query_mock.filter.return_value.all.return_value = []
        return query_mock

    mock_db.query.side_effect = mock_query

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    # Patch OpenAI so first call fails, second call succeeds
    mock_openai_response = MagicMock()
    mock_openai_response.choices = [
        MagicMock(message=MagicMock(content='{"subject": "Fallback", "body": "Fallback body."}'))
    ]

    mock_create = AsyncMock(side_effect=[Exception("First call failed"), mock_openai_response])

    with patch("openai.AsyncOpenAI") as mock_openai_class, patch("os.getenv", return_value="gpt-4.1"):
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create = mock_create
        mock_openai_class.return_value = mock_openai_instance

        response = client.post(
            f"/api/v1/contracts/{contract_id}/redlines/email",
            json={"tone": "professional"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["email"]["subject"] == "Fallback"
        assert data["email"]["body"] == "Fallback body."

        assert mock_create.call_count == 2
        # The second call should use the fallback model
        _, kwargs = mock_create.call_args
        assert kwargs["model"] == "gpt-4.1"

def test_complete_failure(override_deps, mock_user):
    mock_db = MagicMock()

    contract_id = str(uuid.uuid4())
    mock_contract = Contract(
        id=contract_id,
        user_id=mock_user.id,
        filename="test_contract.pdf",
        metadata_json={}
    )

    def mock_query(model):
        query_mock = MagicMock()
        if model == Contract:
            query_mock.filter.return_value.first.return_value = mock_contract
        elif model == ContractClause:
            query_mock.filter.return_value.all.return_value = []
        return query_mock

    mock_db.query.side_effect = mock_query

    def override_get_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_get_db

    # Patch OpenAI so both calls fail
    mock_create = AsyncMock(side_effect=[Exception("First call failed"), Exception("Second call failed")])

    with patch("openai.AsyncOpenAI") as mock_openai_class:
        mock_openai_instance = MagicMock()
        mock_openai_instance.chat.completions.create = mock_create
        mock_openai_class.return_value = mock_openai_instance

        response = client.post(
            f"/api/v1/contracts/{contract_id}/redlines/email",
            json={}
        )

        assert response.status_code == 500
        assert "Email generation failed: Second call failed" in response.json()["detail"]
