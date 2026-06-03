import pytest
from app.main import _parse_iso_date
from datetime import datetime

def test_parse_iso_date_valid():
    dt = _parse_iso_date("2023-10-25T14:30:00Z")
    assert isinstance(dt, datetime)
    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 25
    assert dt.hour == 14
    assert dt.minute == 30
    assert dt.tzinfo is not None

def test_parse_iso_date_valid_no_z():
    dt = _parse_iso_date("2023-10-25T14:30:00")
    assert isinstance(dt, datetime)
    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 25
    assert dt.hour == 14
    assert dt.minute == 30
    assert dt.tzinfo is None

def test_parse_iso_date_valid_just_date():
    dt = _parse_iso_date("2023-10-25")
    assert isinstance(dt, datetime)
    assert dt.year == 2023
    assert dt.month == 10
    assert dt.day == 25

def test_parse_iso_date_empty():
    assert _parse_iso_date("") is None
    assert _parse_iso_date(None) is None

def test_parse_iso_date_invalid_string():
    assert _parse_iso_date("invalid-date") is None
    assert _parse_iso_date("not-a-date") is None
    assert _parse_iso_date("2023-10-25T14:30:00ZEXTRA") is None

def test_parse_iso_date_invalid_type():
    assert _parse_iso_date(123) is None
    assert _parse_iso_date({"date": "2023"}) is None
