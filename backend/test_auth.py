import sys
import os
import uuid

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app, get_current_user
from backend.app.models import User

client = TestClient(app)

def test_unauthenticated_request():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("Test passed: Unauthenticated request returned 401.")

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
    print("Test passed: Authenticated request returned user details.")

    app.dependency_overrides.clear()

if __name__ == "__main__":
    test_unauthenticated_request()
    test_authenticated_request()
