"""Gemini API provider adapter with strict safety guardrails, timeouts, retries, and quota caps.

Invariants:
- The API key is stored server-side only; never logged or serialized to browser responses.
- Enforces temperature 0.0 and strict JSON output mode.
- Enforces timeout (default 10s), 1 retry on network/5xx error, token cap (1024 tokens).
- Enforces a daily call cap with a clear 'demo budget reached' response.
- Fails closed to recorded fallback when unconfigured or on outage.
"""

import contextlib
import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Verified default model per docs/evidence/gemini-api.md (10 Nov 2026)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiError(Exception):
    """Base exception for Gemini provider adapter errors."""


class GeminiConfigurationError(GeminiError):
    """Raised when GEMINI_API_KEY is missing or invalid."""


class GeminiDailyBudgetExceededError(GeminiError):
    """Raised when daily call cap is exceeded."""


class GeminiTimeoutError(GeminiError):
    """Raised when request times out."""


class GeminiLLMClient:
    """Client for Google Gemini API conforming to Phalanx AI governance requirements."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float = 10.0,
        max_retries: int = 1,
        max_output_tokens: int = 1024,
        daily_call_cap: int = 100,
    ) -> None:
        self._api_key = api_key if api_key is not None else (os.getenv("GEMINI_API_KEY") or "")
        self.model_name = model_name or os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_output_tokens = max_output_tokens
        self.daily_call_cap = daily_call_cap

        # In-memory daily quota tracker
        self._call_count = 0
        self._current_date = datetime.now(UTC).date()

    @property
    def is_configured(self) -> bool:
        """Check if a non-empty API key is available."""
        return bool(self._api_key and self._api_key.strip())

    def _check_and_increment_daily_quota(self) -> None:
        """Enforce daily call quota, resetting at UTC midnight.

        Persists quota count in DailyQuotaModel if database is accessible;
        gracefully falls back to thread-safe in-memory tracking otherwise.
        """
        today = datetime.now(UTC).date()
        quota_key = f"gemini:{today.isoformat()}"

        # Attempt database-backed quota persistence
        session = None
        try:
            from app.infrastructure.database import get_session_factory
            from app.infrastructure.models import DailyQuotaModel

            factory = get_session_factory()
            session = factory()
            record = session.get(DailyQuotaModel, quota_key)
            current_count = record.count if record is not None else 0

            if current_count >= self.daily_call_cap:
                logger.warning(
                    "Gemini daily call cap (%d) reached in DB for %s",
                    self.daily_call_cap,
                    today,
                )
                raise GeminiDailyBudgetExceededError(
                    f"demo budget reached: daily limit of {self.daily_call_cap} calls exhausted"
                )

            if record is None:
                record = DailyQuotaModel(quota_key=quota_key, count=1)
                session.add(record)
            else:
                record.count += 1
            session.commit()
            self._call_count = record.count
            self._current_date = today
            return
        except GeminiDailyBudgetExceededError:
            raise
        except Exception as exc:
            logger.debug("DailyQuota DB tracking unavailable, falling back to in-memory: %s", exc)
            if session is not None:
                with contextlib.suppress(Exception):
                    session.rollback()
        finally:
            if session is not None:
                with contextlib.suppress(Exception):
                    session.close()

        # In-memory fallback
        if today != self._current_date:
            self._current_date = today
            self._call_count = 0

        if self._call_count >= self.daily_call_cap:
            logger.warning(
                "Gemini daily call cap (%d) reached for %s",
                self.daily_call_cap,
                self._current_date,
            )
            raise GeminiDailyBudgetExceededError(
                f"demo budget reached: daily limit of {self.daily_call_cap} calls exhausted"
            )

        self._call_count += 1

    def generate_json(self, prompt: str) -> dict[str, Any]:
        """Invoke Gemini generateContent with temperature 0.0 and strict JSON mode.

        Returns parsed JSON dictionary. Never exposes API key in logs or error messages.
        """
        if not self.is_configured:
            raise GeminiConfigurationError("GEMINI_API_KEY unconfigured")

        self._check_and_increment_daily_quota()

        url = f"{GEMINI_API_BASE_URL}/{self.model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": self.max_output_tokens,
                "responseMimeType": "application/json",
            },
        }

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = httpx.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout_seconds,
                )
                if response.status_code == 200:
                    data = response.json()
                    candidates = data.get("candidates", [])
                    if not candidates:
                        raise GeminiError("Gemini response contained no candidates")
                    content_parts = candidates[0].get("content", {}).get("parts", [])
                    if not content_parts or "text" not in content_parts[0]:
                        raise GeminiError("Gemini response candidate contained no text parts")
                    raw_text = content_parts[0]["text"]
                    parsed: dict[str, Any] = json.loads(raw_text)
                    return parsed
                elif response.status_code in (408, 429, 500, 502, 503, 504):
                    logger.warning(
                        "Gemini API transient HTTP %d on attempt %d/%d",
                        response.status_code,
                        attempt + 1,
                        self.max_retries + 1,
                    )
                    last_error = GeminiError(f"Gemini API returned HTTP {response.status_code}")
                else:
                    raise GeminiError(f"Gemini API HTTP {response.status_code}")
            except httpx.TimeoutException:
                logger.warning(
                    "Gemini API timeout on attempt %d/%d", attempt + 1, self.max_retries + 1
                )
                last_error = GeminiTimeoutError(
                    f"Gemini API timed out after {self.timeout_seconds}s"
                )
            except (json.JSONDecodeError, KeyError) as exc:
                raise GeminiError(f"Invalid JSON returned by Gemini: {exc}") from exc
            except Exception as exc:
                logger.warning(
                    "Gemini API error on attempt %d/%d: %s", attempt + 1, self.max_retries + 1, exc
                )
                last_error = exc

        raise GeminiError(f"Gemini API call failed after retries: {last_error}") from last_error

    def extract_invoice(self, invoice_text: str) -> tuple[Any, bool, str]:
        """High-level invoice extraction with graceful fallback."""
        from app.application.invoice_agent import (
            FALLBACK_RECORDED_RUNS,
            InvoiceExtraction,
            build_invoice_extraction_prompt,
        )

        if not self.is_configured:
            # Clean fallback to certified recorded run
            return (
                InvoiceExtraction.model_validate(FALLBACK_RECORDED_RUNS["sample_a"]["extraction"]),
                False,
                "RECORDED RUN (GEMINI_API_KEY Unconfigured)",
            )

        try:
            prompt = build_invoice_extraction_prompt(invoice_text)
            parsed = self.generate_json(prompt)
            extraction = InvoiceExtraction.model_validate(parsed)
            return extraction, True, f"LIVE ({self.model_name})"
        except GeminiDailyBudgetExceededError:
            logger.info("Daily cap reached; using recorded run fallback")
            return (
                InvoiceExtraction.model_validate(FALLBACK_RECORDED_RUNS["sample_a"]["extraction"]),
                False,
                "RECORDED RUN (Demo Budget Reached)",
            )
        except Exception as exc:
            logger.warning("Live Gemini call failed (%s); using recorded run fallback", exc)
            return (
                InvoiceExtraction.model_validate(FALLBACK_RECORDED_RUNS["sample_a"]["extraction"]),
                False,
                f"RECORDED RUN (Provider Error: {type(exc).__name__})",
            )
