import sys
import os
import hashlib

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from backend.app.parser import compute_file_hash

def test_compute_file_hash_basic():
    # Basic test
    file_bytes = b"Hello, World!"
    expected_hash = hashlib.sha256(file_bytes).hexdigest()
    assert compute_file_hash(file_bytes) == expected_hash

def test_compute_file_hash_empty():
    # Empty bytes test
    file_bytes = b""
    expected_hash = hashlib.sha256(file_bytes).hexdigest()
    assert compute_file_hash(file_bytes) == expected_hash

def test_compute_file_hash_large():
    # Larger bytes test
    file_bytes = b"A" * 1000000
    expected_hash = hashlib.sha256(file_bytes).hexdigest()
    assert compute_file_hash(file_bytes) == expected_hash
