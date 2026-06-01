import sys
import os
import hashlib
from unittest.mock import MagicMock, patch

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.parser import (
    compute_file_hash,
    normalize_contract_text,
    compute_text_hash,
    _slugify,
    extract_contract_metadata,
    standardized_filename,
    extract_text_from_pdf,
)

def test_compute_file_hash_empty():
    assert compute_file_hash(b"") == hashlib.sha256(b"").hexdigest()

def test_compute_file_hash_basic():
    data = b"hello world"
    assert compute_file_hash(data) == hashlib.sha256(data).hexdigest()

def test_normalize_contract_text_none():
    assert normalize_contract_text(None) == ""

def test_normalize_contract_text_basic():
    assert normalize_contract_text("  hello \t world  ") == "hello world"

def test_normalize_contract_text_newlines():
    text = "line1\r\nline2\n\n\n\nline3"
    assert normalize_contract_text(text) == "line1\nline2\n\nline3"

def test_normalize_contract_text_spaces():
    text = "word1    word2\t\tword3"
    assert normalize_contract_text(text) == "word1 word2 word3"

def test_compute_text_hash():
    text = " hello \n world "
    norm = normalize_contract_text(text)
    expected = hashlib.sha256(("text:" + norm).encode("utf-8")).hexdigest()
    assert compute_text_hash(text) == expected

def test_slugify_empty():
    assert _slugify(None) == ""
    assert _slugify("") == ""
    assert _slugify("   ") == ""

def test_slugify_basic():
    assert _slugify("Hello World") == "Hello-World"

def test_slugify_special_chars():
    assert _slugify("My #1 Company, Inc.") == "My-1-Company-Inc"

def test_slugify_ampersand():
    assert _slugify("A & B") == "A-and-B"

def test_extract_contract_metadata_empty():
    res = extract_contract_metadata(None)
    assert res == {
        "contract_date": None,
        "company": None,
        "contract_type": None,
        "expiry_date": None,
        "renewal_notice_days": None,
        "contract_term": None,
    }

def test_extract_contract_metadata_basic():
    text = """
    NON-DISCLOSURE AGREEMENT

    This Agreement is entered into by and between Acme Corp, hereinafter referred to as "Company",
    and John Doe.

    Dated: 05/17/2026

    This agreement shall expire on June 1, 2030.
    Party must give 30 days prior to renewal notice.
    Initial term of one (1) year.
    """
    res = extract_contract_metadata(text)
    assert res["contract_type"] == "Non-Disclosure Agreement"
    assert res["company"] == "Acme Corp"
    assert res["contract_date"] == "2026-05-17"
    assert res["expiry_date"] == "2030-06-01"
    assert res["renewal_notice_days"] == 30
    assert res["contract_term"].lower() == "term of one (1) year"

def test_extract_contract_metadata_no_match():
    text = "Just some random text with no legal meaning."
    res = extract_contract_metadata(text)
    assert res["contract_type"] is None
    assert res["company"] is None
    assert res["contract_date"] is None
    assert res["expiry_date"] is None
    assert res["renewal_notice_days"] is None
    assert res["contract_term"] is None

def test_standardized_filename_all_fields():
    meta = {
        "contract_date": "2024-01-01",
        "company": "Acme Corp",
        "contract_type": "Master Services Agreement"
    }
    fname = standardized_filename(meta, "2000-01-01")
    assert fname == "2024-01-01__Acme-Corp__Master-Services-Agreement.pdf"

def test_standardized_filename_missing_fields():
    meta = {}
    fname = standardized_filename(meta, "2024-01-01")
    assert fname == "2024-01-01__unknown-company__contract.pdf"

@patch('backend.app.parser.fitz.open')
def test_extract_text_from_pdf(mock_fitz_open):
    # Setup mock document
    mock_doc = MagicMock()
    mock_page1 = MagicMock()
    mock_page1.get_text.return_value = "Page 1 text"
    mock_page2 = MagicMock()
    mock_page2.get_text.return_value = "Page 2 text"

    # Configure document to return pages
    mock_doc.__len__.return_value = 2
    mock_doc.load_page.side_effect = [mock_page1, mock_page2]

    mock_fitz_open.return_value = mock_doc

    fake_pdf_bytes = b"fake pdf data"
    file_hash, extracted_text = extract_text_from_pdf(fake_pdf_bytes)

    assert file_hash == compute_file_hash(fake_pdf_bytes)
    assert extracted_text == "Page 1 text\nPage 2 text"
    mock_fitz_open.assert_called_once_with(stream=fake_pdf_bytes, filetype="pdf")
    mock_doc.close.assert_called_once()
