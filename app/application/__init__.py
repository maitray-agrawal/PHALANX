"""Application layer for PHALANX.

Coordinates domain logic and ports for all system entrypoints.
"""

from app.application.advisory_signals import (
    AdvisorySignalBundle,
    CompositeAdvisoryPipeline,
    HeuristicRiskScanner,
    SyntheticInjectionClassifier,
    VelocityAnomalyDetector,
    VelocityScoreResult,
)
from app.application.dtos import (
    AuthorizationResponseDTO,
    AuthorizeTransactionCommand,
    HealthStatusDTO,
)
from app.application.grounding import GroundedExplanationValidator
from app.application.intent_extractor import (
    IntentExtractor,
    MandateSummary,
    TransactionIntentDraft,
)
from app.application.llm_client import (
    LLMClient,
    LLMMessage,
    LLMResponse,
    LLMUsage,
    ProviderAgnosticLLMClient,
    TokenCapExceededError,
)
from app.application.memory import (
    DeterministicKnowledgeBase,
    PrincipalSessionMemory,
)
from app.application.services import AuthorizationService, HealthService

__all__ = [
    "AdvisorySignalBundle",
    "AuthorizationResponseDTO",
    "AuthorizationService",
    "AuthorizeTransactionCommand",
    "CompositeAdvisoryPipeline",
    "DeterministicKnowledgeBase",
    "GroundedExplanationValidator",
    "HealthService",
    "HealthStatusDTO",
    "HeuristicRiskScanner",
    "IntentExtractor",
    "LLMClient",
    "LLMMessage",
    "LLMResponse",
    "LLMUsage",
    "MandateSummary",
    "PrincipalSessionMemory",
    "ProviderAgnosticLLMClient",
    "SyntheticInjectionClassifier",
    "TokenCapExceededError",
    "TransactionIntentDraft",
    "VelocityAnomalyDetector",
    "VelocityScoreResult",
]
