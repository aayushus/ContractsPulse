import pytest
from backend.app.parser import normalize_contract_text

def test_normalize_contract_text_empty():
    assert normalize_contract_text("") == ""
    assert normalize_contract_text(None) == ""

def test_normalize_contract_text_strip():
    assert normalize_contract_text("  hello world  ") == "hello world"

def test_normalize_contract_text_crlf():
    # Only \r\n? is replaced with \n
    # Note: re.sub(r"\r\n?", "\n", t)
    assert normalize_contract_text("hello\r\nworld") == "hello\nworld"
    assert normalize_contract_text("hello\rworld") == "hello\nworld"

def test_normalize_contract_text_spaces_tabs():
    # Only replaces 1 or more spaces/tabs with a single space
    # Note: re.sub(r"[ \t]+", " ", t)
    assert normalize_contract_text("hello   world") == "hello world"
    assert normalize_contract_text("hello\tworld") == "hello world"
    assert normalize_contract_text("hello \t world") == "hello world"

def test_normalize_contract_text_multiple_newlines():
    # 2 newlines should remain 2 newlines
    assert normalize_contract_text("hello\n\nworld") == "hello\n\nworld"
    # 3 newlines should become 2 newlines
    assert normalize_contract_text("hello\n\n\nworld") == "hello\n\nworld"
    # 4 newlines should become 2 newlines
    assert normalize_contract_text("hello\n\n\n\nworld") == "hello\n\nworld"

def test_normalize_contract_text_complex():
    text = "   This \t is   a \r\n\r\n\r\ntest  \n\n\n\n  "
    expected = "This is a \n\ntest"
    assert normalize_contract_text(text) == expected
