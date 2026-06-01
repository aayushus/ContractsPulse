import sys
import os

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from backend.app.main import app, get_password_hash, verify_password

client = TestClient(app)

def test_unauthenticated_request():
    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401, f"Expected 401, got {response.status_code}"
    print("Test passed: Unauthenticated request returned 401.")

def test_get_password_hash():
    password = "MySecurePassword123!"
    hashed_password = get_password_hash(password)

    # Check that it returns a string and is not the same as the plaintext password
    assert isinstance(hashed_password, str)
    assert hashed_password != password

    # Check that it produces a valid hash that can be verified
    assert verify_password(password, hashed_password) is True

def test_get_password_hash_different_salts():
    password = "AnotherPassword456!"
    hash1 = get_password_hash(password)
    hash2 = get_password_hash(password)

    # Hashes of the same password should differ due to random salting
    assert hash1 != hash2

if __name__ == "__main__":
    test_unauthenticated_request()
    test_get_password_hash()
    test_get_password_hash_different_salts()
