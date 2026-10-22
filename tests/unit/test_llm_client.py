"""Unit tests for ProviderAgnosticLLMClient: quotas, timeouts, retries, and costs."""

import json

import pytest
from pydantic import BaseModel, Field

from app.application.llm_client import (
    CostCapExceededError,
    LLMError,
    LLMMessage,
    ProviderAgnosticLLMClient,
    TokenCapExceededError,
)


class MockIntentSchema(BaseModel):
    recipient: str = Field(...)
    cents: int = Field(...)


def test_llm_client_basic_generation() -> None:
    client = ProviderAgnosticLLMClient(token_cap=10_000, cost_cap=1.0)
    messages = [
        LLMMessage(role="system", content="You are a helpful assistant."),
        LLMMessage(role="user", content="Hello, world!"),
    ]

    response = client.generate(messages, identity_id="user-1")

    assert response.content is not None
    assert response.usage.prompt_tokens > 0
    assert response.usage.completion_tokens > 0
    assert (
        response.usage.total_tokens
        == response.usage.prompt_tokens + response.usage.completion_tokens
    )
    assert response.usage.cost_usd >= 0.0


def test_llm_client_enforces_token_cap() -> None:
    # Set tiny token cap of 10 tokens
    client = ProviderAgnosticLLMClient(token_cap=10, cost_cap=10.0)
    messages = [
        LLMMessage(
            role="user", content="This is a test prompt that easily exceeds ten tokens in length."
        ),
    ]

    with pytest.raises(TokenCapExceededError) as exc_info:
        client.generate(messages, identity_id="budget-user")

    assert "Token cap exceeded for identity 'budget-user'" in str(exc_info.value)


def test_llm_client_enforces_cost_cap() -> None:
    # Set cost cap of $0.000001
    client = ProviderAgnosticLLMClient(token_cap=1_000_000, cost_cap=0.000001)

    # First call uses up the tiny budget
    messages = [LLMMessage(role="user", content="Test message")]
    client.generate(messages, identity_id="cost-user")

    # Second call must raise CostCapExceededError
    with pytest.raises(CostCapExceededError) as exc_info:
        client.generate(messages, identity_id="cost-user")

    assert "Cost cap exceeded for identity 'cost-user'" in str(exc_info.value)


def test_llm_client_retries_on_transient_failure() -> None:
    client = ProviderAgnosticLLMClient(max_retries=2, timeout_seconds=1.0)

    call_count = 0

    def flaky_backend(_msgs, _temp, _model):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("Transient connection reset")
        return "Recovered response"

    client.set_backend_generator(flaky_backend)

    response = client.generate([LLMMessage(role="user", content="Ping")])
    assert response.content == "Recovered response"
    assert call_count == 2


def test_llm_client_raises_after_max_retries_exhausted() -> None:
    client = ProviderAgnosticLLMClient(max_retries=1, timeout_seconds=1.0)

    def failing_backend(_msgs, _temp, _model):
        raise ConnectionError("Persistent server down")

    client.set_backend_generator(failing_backend)

    with pytest.raises(LLMError) as exc_info:
        client.generate([LLMMessage(role="user", content="Ping")])

    assert "LLM call failed after 2 attempts" in str(exc_info.value)


def test_llm_client_structured_json_generation() -> None:
    client = ProviderAgnosticLLMClient()

    def json_backend(_msgs, temp, _model):
        assert temp == 0.0
        return json.dumps({"recipient": "vendor-alpha", "cents": 4500})

    client.set_backend_generator(json_backend)

    response = client.generate(
        [LLMMessage(role="user", content="Pay vendor-alpha 4500 cents")],
        temperature=0.0,
        response_model=MockIntentSchema,
    )

    assert response.structured_data is not None
    assert response.structured_data["recipient"] == "vendor-alpha"
    assert response.structured_data["cents"] == 4500
