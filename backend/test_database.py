import sys
import os
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app.database import get_db, _register_pgvector

@patch("backend.app.database.register_vector")
def test_register_pgvector_success(mock_register_vector):
    mock_dbapi_connection = MagicMock()
    mock_connection_record = MagicMock()

    _register_pgvector(mock_dbapi_connection, mock_connection_record)

    mock_register_vector.assert_called_once_with(mock_dbapi_connection)


@patch("backend.app.database.register_vector")
def test_register_pgvector_exception(mock_register_vector):
    mock_register_vector.side_effect = Exception("Test exception")
    mock_dbapi_connection = MagicMock()
    mock_connection_record = MagicMock()

    # This should not raise an exception
    _register_pgvector(mock_dbapi_connection, mock_connection_record)

    mock_register_vector.assert_called_once_with(mock_dbapi_connection)


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
