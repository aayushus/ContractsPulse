import sys
import os

# Add the backend directory to sys.path so we can import app
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.parser import extract_contract_metadata

def test_extract_contract_type():
    text = "THIS IS A NON-DISCLOSURE AGREEMENT\n\nbla bla"
    metadata = extract_contract_metadata(text)
    assert metadata["contract_type"] == "This Is A Non-Disclosure Agreement"

    text2 = "Some text\n\nSTATEMENT OF WORK\nbetween parties"
    metadata2 = extract_contract_metadata(text2)
    assert metadata2["contract_type"] == "Statement Of Work"

def test_extract_company():
    text = "This contract is made by and between Acme Corp, hereinafter referred to as..."
    metadata = extract_contract_metadata(text)
    assert metadata["company"] == "Acme Corp"

    text2 = "This agreement is by and between The Cool Company, hereinafter..."
    metadata2 = extract_contract_metadata(text2)
    assert metadata2["company"] == "Cool Company" # "the " prefix is dropped

def test_extract_contract_date():
    text = "The contract date is 05/17/2026."
    metadata = extract_contract_metadata(text)
    assert metadata["contract_date"] == "2026-05-17"

    text2 = "Dated May 17, 2026."
    metadata2 = extract_contract_metadata(text2)
    assert metadata2["contract_date"] == "2026-05-17"

def test_extract_expiry_date():
    text = "This agreement shall expire on December 31, 2028."
    metadata = extract_contract_metadata(text)
    assert metadata["expiry_date"] == "2028-12-31"

    text2 = "Valid until January 1, 2029"
    metadata2 = extract_contract_metadata(text2)
    assert metadata2["expiry_date"] == "2029-01-01"

def test_extract_renewal_notice_days():
    text = "Must give 30 days prior to renewal."
    metadata = extract_contract_metadata(text)
    assert metadata["renewal_notice_days"] == 30

    text2 = "Notice must be given 60 calendar days before expiration."
    metadata2 = extract_contract_metadata(text2)
    assert metadata2["renewal_notice_days"] == 60

def test_extract_contract_term():
    text = "This agreement has an initial term of one (1) year."
    metadata = extract_contract_metadata(text)
    assert metadata["contract_term"] == "term of one (1) year"

    text2 = "Valid for a period of 12 months."
    metadata2 = extract_contract_metadata(text2)
    assert metadata2["contract_term"] == "for a period of 12 month"

def test_empty_string():
    metadata = extract_contract_metadata("")
    assert metadata["contract_type"] is None
    assert metadata["company"] is None
    assert metadata["contract_date"] is None
    assert metadata["expiry_date"] is None
    assert metadata["renewal_notice_days"] is None
    assert metadata["contract_term"] is None

def test_none_input():
    metadata = extract_contract_metadata(None)
    assert metadata["contract_type"] is None
    assert metadata["company"] is None
    assert metadata["contract_date"] is None
    assert metadata["expiry_date"] is None
    assert metadata["renewal_notice_days"] is None
    assert metadata["contract_term"] is None

def test_no_matches():
    text = "Just a random document without any specific keywords."
    metadata = extract_contract_metadata(text)
    assert metadata["contract_type"] is None
    assert metadata["company"] is None
    assert metadata["contract_date"] is None
    assert metadata["expiry_date"] is None
    assert metadata["renewal_notice_days"] is None
    assert metadata["contract_term"] is None
