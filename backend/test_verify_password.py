from backend.app.main import verify_password, get_password_hash

def test_verify_password_correct():
    """Test that verify_password returns True for a matching password."""
    password = "secure_password123"
    hashed = get_password_hash(password)
    assert verify_password(password, hashed) is True, "Expected True for correct password"

def test_verify_password_incorrect():
    """Test that verify_password returns False for an incorrect password."""
    password = "secure_password123"
    wrong_password = "wrong_password"
    hashed = get_password_hash(password)
    assert verify_password(wrong_password, hashed) is False, "Expected False for incorrect password"

def test_verify_password_malformed_hash():
    """Test that verify_password handles malformed hashes gracefully and returns False."""
    password = "secure_password123"
    malformed_hash = "not_a_valid_bcrypt_hash"
    assert verify_password(password, malformed_hash) is False, "Expected False for malformed hash"
