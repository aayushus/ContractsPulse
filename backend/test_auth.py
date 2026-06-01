import sys
import os
import jwt
from unittest.mock import patch, MagicMock

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.database import get_db
from backend.app.models import User
import uuid

client = TestClient(app)

def test_unauthenticated_request():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    assert response.json()["detail"] == "Not authenticated"
    print("Test passed: Unauthenticated request returned 401.")

def test_invalid_token_payload():
    with patch("backend.app.main.jwt.decode") as mock_decode:
        mock_decode.return_value = {"other_key": "value"} # Missing "sub"
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
        # The /api/v1/auth/me endpoint probably returns the user details.
        # We just need to check it didn't fail with 401.

    app.dependency_overrides.clear()

if __name__ == "__main__":
    test_unauthenticated_request()
    test_invalid_token_payload()
    test_expired_token()
    test_invalid_token()
    test_user_not_found()
    test_valid_user()
