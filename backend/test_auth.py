import sys
import os
import jwt
from datetime import datetime, timedelta, timezone

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app, create_access_token, JWT_SECRET, JWT_ALGORITHM

client = TestClient(app)

def test_unauthenticated_request():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("Test passed: Unauthenticated request returned 401.")

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
