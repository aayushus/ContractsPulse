import sys
import os
import hashlib
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.parser import _slugify, compute_file_hash, normalize_contract_text, extract_contract_metadata

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


def test_extract_contract_metadata_empty():
    res = extract_contract_metadata("")
    assert res == {
        "contract_date": None,
        "company": None,
        "contract_type": None,
        "expiry_date": None,
        "renewal_notice_days": None,
        "contract_term": None,
    }

    res_none = extract_contract_metadata(None)
    assert res_none == {
        "contract_date": None,
        "company": None,
        "contract_type": None,
        "expiry_date": None,
        "renewal_notice_days": None,
        "contract_term": None,
    }

def test_extract_contract_metadata_contract_type():
    text = "MASTER SERVICE AGREEMENT\nThis agreement is entered into..."
    res = extract_contract_metadata(text)
    assert res["contract_type"] == "Master Service Agreement"

def test_extract_contract_metadata_company():
    text = "This Agreement is made by and between Acme Corp, hereinafter referred to as 'Company', and..."
    res = extract_contract_metadata(text)
    assert res["company"] == "Acme"

    # Test stripping "the" prefix
    text2 = "This Agreement is made by and between The Global Entity, hereinafter referred to as 'Company', and..."
    res2 = extract_contract_metadata(text2)
    assert res2["company"] == "Global Entity"

    # Test suffix stripping variations
    text3 = "This Agreement is made by and between Acme Co., Ltd., hereinafter referred to as 'Company', and..."
    res3 = extract_contract_metadata(text3)
    assert res3["company"] == "Acme"

    text4 = "This Agreement is made by and between Acme LLC, hereinafter referred to as 'Company', and..."
    res4 = extract_contract_metadata(text4)
    assert res4["company"] == "Acme"

def test_extract_contract_metadata_contract_date():
    text = "Effective as of 05/17/2026, by and between..."
    res = extract_contract_metadata(text)
    assert res["contract_date"] == "2026-05-17"

    text2 = "This Agreement is dated May 17, 2026..."
    res2 = extract_contract_metadata(text2)
    assert res2["contract_date"] == "2026-05-17"

    # 2 digit year
    text3 = "Effective as of 05/17/26, by and between..."
    res3 = extract_contract_metadata(text3)
    assert res3["contract_date"] == "2026-05-17"

def test_extract_contract_metadata_expiry_date():
    text = "This Agreement shall expire on October 31, 2028."
    res = extract_contract_metadata(text)
    assert res["expiry_date"] == "2028-10-31"

    text2 = "expiration date: 12/31/2029"
    res2 = extract_contract_metadata(text2)
    assert res2["expiry_date"] == "2029-12-31"

def test_extract_contract_metadata_renewal_notice_days():
    text = "Either party may terminate this agreement by providing 60 days prior to renewal."
    res = extract_contract_metadata(text)
    assert res["renewal_notice_days"] == 60

def test_extract_contract_metadata_contract_term():
    text = "This Agreement is for an initial term of one (1) year."
    res = extract_contract_metadata(text)
    assert res["contract_term"] == "term of one (1) year"

def test_extract_contract_metadata_full():
    text = """
    NON-DISCLOSURE AGREEMENT

    This Non-Disclosure Agreement (the "Agreement") is made by and between
    Super Secret Startup Inc., hereinafter referred to as "Disclosing Party",
    and ABC Corp.

    Effective as of January 01, 2025.

    The initial term of two (2) years shall commence on the effective date.
    This Agreement shall expire on January 01, 2027.
    Either party may terminate by giving 30 days prior to the expiration.
    """
    res = extract_contract_metadata(text)
    assert res["contract_type"] == "Non-Disclosure Agreement"
    assert res["company"] == "Super Secret Startup"
    assert res["contract_date"] == "2025-01-01"
    assert res["contract_term"] == "term of two (2) year"
    assert res["expiry_date"] == "2027-01-01"
    assert res["renewal_notice_days"] == 30
