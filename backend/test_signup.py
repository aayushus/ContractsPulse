import sys
import os
import pytest
from unittest.mock import MagicMock, patch

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app, get_db
from backend.app.models import User

@pytest.fixture(autouse=True)
def mock_startup_event():
    with patch("backend.app.main.engine.begin"):
        with patch("backend.app.main.Base.metadata.create_all"):
            yield

@pytest.fixture
def mock_db():
    mock_session = MagicMock()
    # Mocking query chain: db.query().filter().first()
    # By default, first() returns None (no existing user)
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_session.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.first.return_value = None

    # Mock user object for successful insertion
    mock_user = User(email="test@example.com", hashed_password="hashed")
    mock_user.id = 1

    # We can mock refresh to set an id
    def mock_refresh(obj):
        if isinstance(obj, User):
            obj.id = 1
    mock_session.refresh.side_effect = mock_refresh

    return mock_session

@pytest.fixture
def client(mock_db):
    def get_mock_db():
        yield mock_db

    app.dependency_overrides[get_db] = get_mock_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()

@patch('backend.app.main.is_signup_disabled', return_value=True)
def test_signup_disabled(mock_is_disabled, client):
    response = client.post("/api/v1/auth/signup", json={"email": "test@example.com", "password": "password"})
    assert response.status_code == 403
    assert response.json()["detail"] == "User registration is currently disabled."

@patch('backend.app.main.is_signup_disabled', return_value=False)
def test_signup_invalid_email(mock_is_disabled, client):
    response = client.post("/api/v1/auth/signup", json={"email": "invalidemail", "password": "password"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid email address."

@patch('backend.app.main.is_signup_disabled', return_value=False)
def test_signup_short_password(mock_is_disabled, client):
    response = client.post("/api/v1/auth/signup", json={"email": "test@example.com", "password": "123"})
    assert response.status_code == 400
    assert response.json()["detail"] == "Password must be at least 8 characters long."

@patch('backend.app.main.is_signup_disabled', return_value=False)
def test_signup_existing_user(mock_is_disabled, client, mock_db):
    # Setup mock DB to return an existing user
    mock_db.query.return_value.filter.return_value.first.return_value = User(email="test@example.com")

    response = client.post("/api/v1/auth/signup", json={"email": "test@example.com", "password": "password"})
    assert response.status_code == 400
    assert response.json()["detail"] == "A user with this email already exists."

@patch('backend.app.main.is_signup_disabled', return_value=False)
def test_signup_success(mock_is_disabled, client, mock_db):
    response = client.post("/api/v1/auth/signup", json={"email": "test@example.com", "password": "password"})
    assert response.status_code == 200
    json_data = response.json()
    assert "access_token" in json_data
    assert json_data["token_type"] == "bearer"
    assert "user" in json_data
    assert json_data["user"]["email"] == "test@example.com"

    # Verify DB calls
    assert mock_db.add.called
    assert mock_db.commit.called
    assert mock_db.refresh.called
