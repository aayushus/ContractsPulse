import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.parser import _slugify

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
