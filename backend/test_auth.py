import sys
import os
import uuid
import jwt
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app, create_access_token, get_current_user, JWT_SECRET, JWT_ALGORITHM
from backend.app.database import get_db
from backend.app.models import User

client = TestClient(app)

def test_unauthenticated_request():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    assert response.json()["detail"] == "Not authenticated"

def test_invalid_token_payload():
    with patch("backend.app.main.jwt.decode") as mock_decode:
        mock_decode.return_value = {"other_key": "value"}
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer dummy_token"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid token payload."

def test_expired_token():
    with patch("backend.app.main.jwt.decode") as mock_decode:
        mock_decode.side_effect = jwt.ExpiredSignatureError()
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer dummy_token"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Token has expired."

def test_invalid_token():
    with patch("backend.app.main.jwt.decode") as mock_decode:
        mock_decode.side_effect = jwt.InvalidTokenError()
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer dummy_token"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid authentication credentials."

def test_user_not_found():
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = None

    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with patch("backend.app.main.jwt.decode") as mock_decode:
        mock_decode.return_value = {"sub": str(uuid.uuid4())}
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer dummy_token"})
        assert response.status_code == 401
        assert response.json()["detail"] == "User not found."

    app.dependency_overrides.clear()

def test_valid_user():
    mock_user = User(id=uuid.uuid4(), email="test@example.com", hashed_password="pwd")
    mock_db = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_user

    def override_get_db():
        try:
            yield mock_db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with patch("backend.app.main.jwt.decode") as mock_decode:
        mock_decode.return_value = {"sub": str(mock_user.id)}
        response = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer dummy_token"})
        assert response.status_code == 200

    app.dependency_overrides.clear()

def test_authenticated_request():
    mock_user = User(
        id=uuid.uuid4(),
        email="testuser@example.com",
        hashed_password="hashed_password"
    )

    def override_get_current_user():
        return mock_user

    app.dependency_overrides[get_current_user] = override_get_current_user

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    data = response.json()
    assert data["id"] == str(mock_user.id)
    assert data["email"] == mock_user.email

    app.dependency_overrides.clear()

def test_create_access_token_default_expiration():
    data = {"sub": "test_user"}
    token = create_access_token(data)

    # Verify token decoding
    decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert decoded["sub"] == "test_user"

    # Check expiration is around 15 minutes from now
    assert "exp" in decoded
    exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
    expected_exp = datetime.now(timezone.utc) + timedelta(minutes=15)

    # Allow 5 seconds diff for execution time
    diff = abs((exp_time - expected_exp).total_seconds())
    assert diff < 5

def test_create_access_token_custom_expiration():
    data = {"sub": "test_custom_user"}
    expires_delta = timedelta(days=1)
    token = create_access_token(data, expires_delta=expires_delta)

    decoded = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert decoded["sub"] == "test_custom_user"

    assert "exp" in decoded
    exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
    expected_exp = datetime.now(timezone.utc) + expires_delta

    diff = abs((exp_time - expected_exp).total_seconds())
    assert diff < 5

if __name__ == "__main__":
    test_unauthenticated_request()
    test_create_access_token_default_expiration()
    test_create_access_token_custom_expiration()
