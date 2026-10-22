# ML_SPEC - Machine Learning & LLM Assistant Specification

Owner prompt: P10

> [!IMPORTANT]
> **Prototype Declaration**: PHALANX is an architectural authorization layer and sandbox security prototype evaluated on synthetic data. It is NOT a trained commercial fraud detection engine, does NOT claim real-world fraud accuracy, and does NOT process real money.

---

## 1. Thesis & Non-Authority Boundary

1. **The LLM is Never in the Authorization Path**:
   - The LLM proposes candidate transaction parameters from natural language.
   - The deterministic policy engine in `app/domain` evaluates the rules.
   - Humans authorize exceptions (step-ups).
2. **One-Way Asymmetric Escalation**:
   - Heuristics, ML classifiers, and advisory signals may ONLY raise decision severity (`ALLOW` -> `STEP_UP` -> `DENY`).
   - Advisory signals can NEVER lower a decision (enforced by `guard_advisory_escalation`).
3. **Zero Secrets in Prompts**:
   - The model is never supplied with tokens, client secrets, database connection strings, or private keys.
   - The model is NEVER provided with money-moving execution tools or database access.

---

## 2. Delimiter Isolation & Untrusted Text

All user-supplied natural language, invoice descriptions, and merchant text are treated strictly as untrusted data and encapsulated inside explicit boundary delimiters:

```
<<<UNTRUSTED_USER_INPUT
{untrusted_user_text}
>>>
```

### Sanitization & Defanging
- Any literal occurrence of `>>>` within the untrusted text is automatically sanitized to `]]]` before prompt assembly to prevent delimiter escape injection attacks.
- System prompt instructions explicitly state that directives inside `<<<UNTRUSTED_USER_INPUT ... >>>` are raw data and cannot override system policies or review requirements.

---

## 3. Provider-Agnostic LLM Client

Implemented in `app/application/llm_client.py`:
- **Model Name in Config**: `settings.llm_model_name` (default: `gpt-4o-mini`).
- **Timeouts & Retries**: `settings.llm_timeout_seconds` (default: 5.0s) with exponential retry backoff (`settings.llm_max_retries = 2`).
- **Per-Identity Quota Caps**:
  - Token cap: `settings.llm_token_cap_per_identity` (default: 50,000 tokens).
  - Cost cap: `settings.llm_cost_cap_dollars_per_identity` (default: $2.00 USD).
  - Quota breaches raise `TokenCapExceededError` or `CostCapExceededError`.
- **Zero Secret Defaults**: API keys are injected via environment; client includes a deterministic simulation double for offline testing.

---

## 4. Intent Extraction Specification

Implemented in `app/application/intent_extractor.py`:
- **Temperature**: Strictly `0.0`.
- **Output Schema**: Strict Pydantic model with `extra="forbid"`.

```python
class TransactionIntentDraft(BaseModel):
    model_config = {"extra": "forbid"}

    recipient_id: str = Field(min_length=1, max_length=100)
    amount_minor: int = Field(ge=1, le=100_000_000)  # Integer cents
    currency: str = Field(default="USD", min_length=3, max_length=3)
    purpose: str = Field(min_length=1, max_length=200)
```

### Context Visibility
The model receives ONLY:
1. Registered payee display names allowlist.
2. Sanitized active mandate summary (limits, currency, allowed purposes).
3. Delimited untrusted user text.

---

## 5. Grounded Explanation Validator

Implemented in `app/application/grounding.py`:
When explaining an authorization decision, the assistant's reply text must strictly reflect the authoritative `AuthorizationResponseDTO`:

### Validation Checks
1. **Decision ID**: Exact `request_id` must appear in candidate explanation.
2. **Decision Outcome**: Exact decision (`ALLOW`, `STEP_UP`, `DENY`) must appear; contradictory outcomes are rejected.
3. **Payee Allowlist**: If payee is mentioned, it MUST match the expected recipient.
4. **Numerical Boundary**: Any numeric amount mentioned must exactly match the intent amount, threshold limits, or request ID. Hallucinated numbers trigger validation failure.

### Fallback Behavior
On ANY validation failure, the candidate text is discarded and replaced with the deterministic template:
```
Decision: {record.decision.value} for request {record.request_id} ({currency} {amount_dollars} to payee '{recipient_id}'). Reason codes: [{codes_str}]. Details: {reasons_str}.
```

---

## 6. Runtime Memory & Deterministic Knowledge Base

Implemented in `app/application/memory.py`:
- **PrincipalSessionMemory**: Scoped strictly to the authenticated `principal_id`. Preserves the last N turns (default: 5) and maintains a rolling summary capped at 500 characters.
- **DeterministicKnowledgeBase**:
  - Key-addressed store for: `policy_spec`, `mandate_summary`, `recent_decisions`, `step_up`, `minor_units`, `ledger`, `mandate_seal`.
  - **Truthfulness Invariant**: Any query outside registered knowledge returns:
    ```
    "I do not know."
    ```
    Never invents unverified facts.

---

## 7. Advisory Signals & UI Uncertainty

Implemented in `app/application/advisory_signals.py`:

| Signal | Method | Score / Range | Documented Interpretation (Manual 43) | Recommendation |
|---|---|---|---|---|
| **Heuristic Risk Scanner** | Regex injection patterns | Match / No Match | Direct prompt injection keyword detected | `STEP_UP` |
| **Spending Velocity** | Median & Median Absolute Deviation (MAD) | Robust Z-score: `0.6745 * (x - med) / mad` | `robust_z <= 2.5`: Normal spending velocity<br>`2.5 < robust_z <= 4.0`: Moderate statistical outlier<br>`robust_z > 4.0`: Extreme anomalous volume spike | `ALLOW`<br>`STEP_UP`<br>`DENY` |
| **Synthetic Classifier** | Pure Python TF-IDF + Logistic Regression | Probability $p \in [0.0, 1.0]$ | $p < 0.35$: Low risk<br>$0.35 \le p < 0.70$: Suspicious prompt syntax<br>$p \ge 0.70$: High-confidence injection vector | `ALLOW`<br>`STEP_UP`<br>`DENY` |
