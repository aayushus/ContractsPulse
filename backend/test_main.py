import sys
import os

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)

def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert response.json() == {"message": "ContractsPulse API is running"}
    print("Test passed: Root endpoint returned 200 with correct message.")

if __name__ == "__main__":
    test_root_endpoint()
