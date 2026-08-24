import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from backend.app.chat_service import generate_chat_response
from backend.app.models import Contract, ContractClause

@pytest.mark.asyncio
async def test_generate_chat_response_embedding_fallback():
    # Setup mock data
    contract = Contract(id=1, filename="test.pdf", metadata_json={})

    # We will create clauses that can trigger keyword overlap.
    # Keyword overlap looks for words > 3 chars. "keyword" fits.
    clause1 = ContractClause(
        contract_id=1,
        clause_type="test clause",
        text_content="This contains the magic keyword we are looking for.",
        embedding=[0.1, 0.2]  # Has embedding to enter the try block
    )
    # Mocking risk_level enum or just giving it a dummy string
    clause1.risk_level = MagicMock()
    clause1.risk_level.value = "LOW"

    db_mock = MagicMock()
    # first call is to fetch all clauses
    db_mock.query().filter().all.return_value = [clause1]

    with patch("backend.app.chat_service.openai.AsyncOpenAI") as MockOpenAI:
        mock_client = MagicMock()
        MockOpenAI.return_value = mock_client

        # Make embeddings.create raise an Exception to trigger fallback
        mock_client.embeddings.create = AsyncMock(side_effect=Exception("API Error"))

        # Mock chat.completions.create to just return a dummy response
        mock_chat_response = MagicMock()
        mock_chat_response.choices = [MagicMock()]
        mock_chat_response.choices[0].message.content = "Mocked answer"
        mock_client.chat.completions.create = AsyncMock(return_value=mock_chat_response)

        res = await generate_chat_response(
            contract=contract,
            question="What is the keyword?",
            history=[],
            db=db_mock
        )

        assert res["answer"] == "Mocked answer"
        assert len(res["sources"]) == 1
        assert res["sources"][0]["clause_type"] == "test clause"
