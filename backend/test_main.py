import sys
import os
import pytest
from datetime import datetime, timezone, timedelta

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.main import _parse_iso_date

def test_parse_iso_date_valid_z():
    # Test valid ISO string with Z suffix
    result = _parse_iso_date("2024-05-15T12:00:00Z")
    assert isinstance(result, datetime)
    assert result.year == 2024
    assert result.month == 5
    assert result.day == 15
    assert result.hour == 12
    assert result.minute == 0
    assert result.second == 0
    assert result.tzinfo == timezone.utc

def test_parse_iso_date_valid_offset():
    # Test valid ISO string with positive offset
    result = _parse_iso_date("2024-05-15T12:00:00+02:00")
    assert isinstance(result, datetime)
    assert result.tzinfo == timezone(timedelta(hours=2))

def test_parse_iso_date_valid_no_tz():
    # Test valid ISO string with no timezone
    result = _parse_iso_date("2024-05-15T12:00:00")
    assert isinstance(result, datetime)
    assert result.tzinfo is None

def test_parse_iso_date_empty_string():
    # Test empty string, should return None
    result = _parse_iso_date("")
    assert result is None

def test_parse_iso_date_none():
    # Test None, should return None
    result = _parse_iso_date(None)
    assert result is None

def test_parse_iso_date_invalid_string():
    # Test invalid string, should return None
    result = _parse_iso_date("invalid-date")
    assert result is None
