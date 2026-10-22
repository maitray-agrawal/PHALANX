"""Unit tests for PrincipalSessionMemory and DeterministicKnowledgeBase."""

from app.application.memory import (
    UNKNOWN_RESPONSE,
    DeterministicKnowledgeBase,
    PrincipalSessionMemory,
)


def test_session_memory_scoped_and_capped() -> None:
    memory = PrincipalSessionMemory(
        session_id="sess_123",
        principal_id="corp-finance-01",
        max_turns=3,
        max_summary_chars=120,
    )

    # Add 5 turns (exceeding max_turns=3)
    for i in range(5):
        memory.add_turn(
            role="user" if i % 2 == 0 else "assistant", content=f"Message turn number {i}"
        )

    snapshot = memory.get_context_snapshot()
    assert snapshot["session_id"] == "sess_123"
    assert snapshot["principal_id"] == "corp-finance-01"

    # Only last 3 turns retained
    assert len(snapshot["recent_turns"]) == 3
    assert snapshot["recent_turns"][-1]["content"] == "Message turn number 4"

    # Rolling summary is size-capped
    assert len(memory.rolling_summary) <= 120


def test_knowledge_base_deterministic_key_lookups() -> None:
    kb = DeterministicKnowledgeBase()
    kb.register_mandate_summary(
        "corp-finance-01", "Mandate M1: USD 500.00 limit, Payees: [vendor-1]"
    )
    kb.register_decision_record("corp-finance-01", "req_101: ALLOW $25.00")

    # Policy spec
    policy = kb.lookup_by_key("policy_spec")
    assert "Strict deterministic precedence" in policy or "Precedence" in policy
    assert "Single Transaction Limit" in policy

    # Mandate summary
    mandate = kb.lookup_by_key("mandate_summary", principal_id="corp-finance-01")
    assert "USD 500.00 limit" in mandate

    # FAQ
    faq_stepup = kb.lookup_by_key("step_up")
    assert "step-up approval occurs" in faq_stepup.lower()

    # Recent decisions
    decisions = kb.lookup_by_key("recent_decisions", principal_id="corp-finance-01")
    assert "req_101: ALLOW" in decisions


def test_knowledge_base_unregistered_queries_return_unknown() -> None:
    """Prompt requirement: Outside the deterministic knowledge base: say 'I do not know.'"""
    kb = DeterministicKnowledgeBase()

    # Queries outside the deterministic domain
    unregistered_queries = [
        "What is the weather in Paris tomorrow?",
        "Who won the 2026 World Cup?",
        "What is the company stock ticker symbol?",
        "Can you write a poem about finance?",
        "Tell me a joke about autonomous agents.",
    ]

    for q in unregistered_queries:
        answer = kb.answer_query(q)
        assert answer == UNKNOWN_RESPONSE, (
            f"Expected '{UNKNOWN_RESPONSE}' for '{q}', got '{answer}'"
        )
