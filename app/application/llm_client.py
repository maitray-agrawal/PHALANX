"""Provider-agnostic LLM client with quotas, timeouts, retries, and cost tracking.

Invariants:
- Model name configured via settings, zero secrets in code.
- Hard token and cost caps enforced per identity.
- Configurable timeouts and retries on transient errors.
- Never exposed to money-moving tools or authorization execution.
"""

import json
import logging
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel

from app.infrastructure.config import settings

logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Protocol for provider-agnostic LLM clients."""

    def generate(
        self,
        messages: list["LLMMessage"],
        identity_id: str = "default_identity",
        temperature: float = 0.0,
        response_model: type[BaseModel] | None = None,
    ) -> "LLMResponse":
        """Generate response with quota enforcement."""
        ...


class LLMError(Exception):
    """Base exception for LLM operations."""


class TokenCapExceededError(LLMError):
    """Raised when an identity exceeds its allocated token limit."""


class CostCapExceededError(LLMError):
    """Raised when an identity exceeds its allocated USD cost limit."""


class LLMTimeoutError(LLMError):
    """Raised when LLM request times out."""


@dataclass(frozen=True)
class LLMMessage:
    role: str  # "system", "user", "assistant"
    content: str


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float


@dataclass(frozen=True)
class LLMResponse:
    content: str
    usage: LLMUsage
    model: str
    structured_data: dict[str, Any] | None = None


@dataclass
class IdentityUsageStats:
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    request_count: int = 0


class ProviderAgnosticLLMClient:
    """LLM client with timeouts, exponential retries, and strict per-identity quota enforcement."""

    def __init__(
        self,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        token_cap: int | None = None,
        cost_cap: float | None = None,
        input_cost_per_million: float = 0.15,
        output_cost_per_million: float = 0.60,
    ) -> None:
        self.model_name = model_name or settings.llm_model_name
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds
        self.max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        self.token_cap = token_cap if token_cap is not None else settings.llm_token_cap_per_identity
        self.cost_cap = (
            cost_cap if cost_cap is not None else settings.llm_cost_cap_dollars_per_identity
        )
        self.input_cost_per_million = input_cost_per_million
        self.output_cost_per_million = output_cost_per_million

        # Per-identity budget tracking
        self._identity_budgets: dict[str, IdentityUsageStats] = defaultdict(IdentityUsageStats)

        # Custom handler for pluggable backends (e.g. OpenAI, Anthropic, or mock simulator)
        self._backend_generator: (
            Callable[[list[LLMMessage], float, type[BaseModel] | None], str] | None
        ) = None

    def set_backend_generator(
        self,
        generator: Callable[[list[LLMMessage], float, type[BaseModel] | None], str],
    ) -> None:
        """Inject backend generator for testing or alternative providers."""
        self._backend_generator = generator

    def get_identity_usage(self, identity_id: str) -> IdentityUsageStats:
        """Query cumulative usage metrics for a specific identity."""
        return self._identity_budgets[identity_id]

    def reset_usage(self, identity_id: str | None = None) -> None:
        """Reset usage statistics (for testing or billing cycle resets)."""
        if identity_id:
            self._identity_budgets.pop(identity_id, None)
        else:
            self._identity_budgets.clear()

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count (approx. 4 characters per token)."""
        return max(1, len(text) // 4)

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Calculate estimated cost in USD based on configured rates."""
        cost_in = (prompt_tokens / 1_000_000) * self.input_cost_per_million
        cost_out = (completion_tokens / 1_000_000) * self.output_cost_per_million
        return round(cost_in + cost_out, 6)

    def _check_and_reserve_quota(self, identity_id: str, estimated_prompt_tokens: int) -> None:
        """Enforce strict per-identity quotas before dispatching generation."""
        stats = self._identity_budgets[identity_id]
        if stats.total_tokens + estimated_prompt_tokens > self.token_cap:
            raise TokenCapExceededError(
                f"Token cap exceeded for identity '{identity_id}': "
                f"current={stats.total_tokens}, cap={self.token_cap}"
            )
        if stats.total_cost_usd >= self.cost_cap:
            raise CostCapExceededError(
                f"Cost cap exceeded for identity '{identity_id}': "
                f"current=${stats.total_cost_usd:.4f}, cap=${self.cost_cap:.2f}"
            )

    def generate(
        self,
        messages: list[LLMMessage],
        identity_id: str = "default_identity",
        temperature: float = 0.0,
        response_model: type[BaseModel] | None = None,
    ) -> LLMResponse:
        """Execute model generation with timeouts, retries, and quota tracking."""
        prompt_str = "\n".join(f"{m.role}: {m.content}" for m in messages)
        prompt_tokens = self._estimate_tokens(prompt_str)

        # 1. Enforce quota prior to call
        self._check_and_reserve_quota(identity_id, prompt_tokens)

        # 2. Execute with retry loop
        last_exception: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                start_time = time.time()
                raw_output = self._dispatch(messages, temperature, response_model)
                elapsed = time.time() - start_time
                if elapsed > self.timeout_seconds:
                    raise LLMTimeoutError(
                        f"LLM request timed out after {elapsed:.2f}s "
                        f"(limit: {self.timeout_seconds}s)"
                    )
                break
            except Exception as exc:
                last_exception = exc
                logger.warning(
                    "LLM request attempt %d/%d failed: %s",
                    attempt + 1,
                    self.max_retries + 1,
                    exc,
                )
                if attempt == self.max_retries:
                    raise LLMError(
                        f"LLM call failed after {self.max_retries + 1} attempts: {exc}"
                    ) from exc
                time.sleep(0.05 * (2**attempt))
        else:
            raise LLMError(f"LLM call failed: {last_exception}")

        # 3. Process usage and update accounting
        completion_tokens = self._estimate_tokens(raw_output)
        total_tokens = prompt_tokens + completion_tokens
        call_cost = self._calculate_cost(prompt_tokens, completion_tokens)

        stats = self._identity_budgets[identity_id]
        stats.total_prompt_tokens += prompt_tokens
        stats.total_completion_tokens += completion_tokens
        stats.total_tokens += total_tokens
        stats.total_cost_usd = round(stats.total_cost_usd + call_cost, 6)
        stats.request_count += 1

        usage = LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=call_cost,
        )

        structured_data = None
        if response_model is not None:
            try:
                structured_data = json.loads(raw_output)
            except Exception as exc:
                logger.warning("Failed to parse JSON response into structured model: %s", exc)

        return LLMResponse(
            content=raw_output,
            usage=usage,
            model=self.model_name,
            structured_data=structured_data,
        )

    def _dispatch(
        self,
        messages: list[LLMMessage],
        temperature: float,
        response_model: type[BaseModel] | None,
    ) -> str:
        """Internal dispatch hook."""
        if self._backend_generator:
            return self._backend_generator(messages, temperature, response_model)

        # Default safe mock response adhering to schema if requested
        if response_model:
            schema_keys = response_model.model_fields.keys()
            mock_dict: dict[str, Any] = {}
            for k in schema_keys:
                if k == "recipient_id":
                    mock_dict[k] = "vendor-paypal-sandbox-1"
                elif k == "amount_minor":
                    mock_dict[k] = 2500
                elif k == "currency":
                    mock_dict[k] = "USD"
                elif k == "purpose":
                    mock_dict[k] = "Standard verified subscription renewal"
                else:
                    mock_dict[k] = "simulated_value"
            return json.dumps(mock_dict)

        return "I am the PHALANX assistant. I do not have direct authority to approve payments."
