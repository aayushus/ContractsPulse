import sys
import os
import hashlib
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.parser import _slugify, compute_file_hash, normalize_contract_text

def test_slugify_empty_string():
    assert _slugify("") == ""
    assert _slugify(None) == ""
    assert _slugify("   ") == ""

def test_slugify_normal_string():
    assert _slugify("hello") == "hello"
    assert _slugify("test string") == "test-string"

def test_slugify_uppercase():
    assert _slugify("HELLO") == "HELLO"
    assert _slugify("Test String") == "Test-String"

def test_slugify_special_characters():
    assert _slugify("hello!world") == "hello-world"
    assert _slugify("test@#$string") == "test-string"
    assert _slugify("a.b.c") == "a-b-c"

def test_slugify_multiple_dashes():
    assert _slugify("hello---world") == "hello-world"

def test_slugify_leading_trailing_special():
    assert _slugify("!hello world!") == "hello-world"
    assert _slugify("  --test--  ") == "test"

def test_slugify_ampersand():
    assert _slugify("A & B") == "A-and-B"

def test_slugify_long_string_truncation():
    # 81 characters
    long_str = "a" * 81
    assert _slugify(long_str) == "a" * 80

def test_compute_file_hash_basic():
    file_bytes = b"Hello, World!"
    expected_hash = hashlib.sha256(file_bytes).hexdigest()
    assert compute_file_hash(file_bytes) == expected_hash

def test_compute_file_hash_empty():
    file_bytes = b""
    expected_hash = hashlib.sha256(file_bytes).hexdigest()
    assert compute_file_hash(file_bytes) == expected_hash

def test_normalize_contract_text_empty():
    assert normalize_contract_text("") == ""
    assert normalize_contract_text(None) == ""

def test_normalize_contract_text_strip():
    assert normalize_contract_text("  hello world  ") == "hello world"

def test_normalize_contract_text_crlf():
    assert normalize_contract_text("hello\r\nworld") == "hello\nworld"
    assert normalize_contract_text("hello\rworld") == "hello\nworld"

def test_normalize_contract_text_spaces_tabs():
    assert normalize_contract_text("hello   world") == "hello world"
    assert normalize_contract_text("hello\tworld") == "hello world"
    assert normalize_contract_text("hello \t world") == "hello world"

def test_normalize_contract_text_multiple_newlines():
    assert normalize_contract_text("hello\n\nworld") == "hello\n\nworld"
    assert normalize_contract_text("hello\n\n\nworld") == "hello\n\nworld"
    assert normalize_contract_text("hello\n\n\n\nworld") == "hello\n\nworld"
