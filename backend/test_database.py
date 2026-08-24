import sys
import os
import pytest

from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.models import Contract, User, Base
import uuid
import sqlalchemy
import sqlalchemy.dialects.sqlite.base

from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.database import get_db

@patch("backend.app.database.SessionLocal")
def test_get_db_yields_session_and_closes(mock_session_local):
    mock_session = MagicMock()
    mock_session_local.return_value = mock_session

    db_generator = get_db()
    db = next(db_generator)

    assert db == mock_session
    mock_session.close.assert_not_called()

    with pytest.raises(StopIteration):
        next(db_generator)

    mock_session.close.assert_called_once()

@patch("backend.app.database.SessionLocal")
def test_get_db_closes_on_exception(mock_session_local):
    mock_session = MagicMock()
    mock_session_local.return_value = mock_session

    db_generator = get_db()
    db = next(db_generator)

    assert db == mock_session
    mock_session.close.assert_not_called()

    with pytest.raises(ValueError):
        db_generator.throw(ValueError("Test exception"))

    mock_session.close.assert_called_once()


def test_contract_file_hash_user_id_uniqueness():
    # Mock visit_JSONB to prevent compile errors in sqlite
    sqlalchemy.dialects.sqlite.base.SQLiteTypeCompiler.visit_JSONB = lambda self, type_, **kw: 'JSON'

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db_session = Session()

    user = User(email="test_unique@example.com", hashed_password="pw")
    db_session.add(user)
    db_session.commit()

    contract1 = Contract(filename="a.pdf", file_hash="hash123", user_id=user.id)
    db_session.add(contract1)
    db_session.commit()

    contract2 = Contract(filename="b.pdf", file_hash="hash123", user_id=user.id)
    db_session.add(contract2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Different user can have the same hash
    user2 = User(email="test_unique2@example.com", hashed_password="pw")
    db_session.add(user2)
    db_session.commit()

    contract3 = Contract(filename="c.pdf", file_hash="hash123", user_id=user2.id)
    db_session.add(contract3)
    db_session.commit() # Should succeed
    db_session.close()
