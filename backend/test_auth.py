import sys
import os

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_unauthenticated_request():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("Test passed: Unauthenticated request returned 401.")

if __name__ == "__main__":
    test_unauthenticated_request()
