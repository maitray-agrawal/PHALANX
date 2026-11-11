# Gemini API Documentation & Verification Record

**Date:** 2026-11-11  
**URL:** https://ai.google.dev/gemini-api/docs/models/gemini  
**API Specification:** Gemini API (Developer API v1beta / generateContent)  
**Endpoint:** `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`  
**Supported Models:**
- `gemini-2.5-flash`: Production default in PHALANX. Fast, high-throughput model optimized for structured JSON document extraction and multimodal processing.
- *(Historical / Legacy: `gemini-1.5-flash`, `gemini-1.5-pro`)*

---

## Configuration & Guardrail Rules in PHALANX
1. **API Key Handling:** Key is read exclusively from the server-side environment variable `GEMINI_API_KEY`. It is NEVER exposed to the frontend, browser, network payloads, or server logs.
2. **Output Formatting:** `response_mime_type: "application/json"` with strict response schema enforcing `InvoiceExtraction` properties (`payee`, `account`, `amount_minor`, `currency`, `due_date`, `invoice_number`, `purpose`).
3. **Deterministic Sampling:** `temperature: 0.0`.
4. **Resilience:** Single retry, 10.0s request timeout, 1024 token cap.
5. **Daily Quota & Budget Enforcement:** Persisted daily call count; when quota is exceeded, returns clear error: `demo budget reached: daily limit of {daily_call_cap} calls exhausted`.
6. **Untrusted Prompt Isolation:** Raw invoice text is fenced between structural delimiters `<<<UNTRUSTED_INVOICE_TEXT>>>` and `<<</UNTRUSTED_INVOICE_TEXT>>>` with escaped internal brackets.

---

## Live Call Status
- **Environment Status:** `GEMINI_API_KEY` is not currently set in the environment.
- **Evidence Label:** **`PENDING-HUMAN`** (awaiting user setting `GEMINI_API_KEY` in environment).
- **Fallback Verification:** All four sample invoices fall back cleanly to certified baseline recorded runs (`is_live: false`, `status_label: "RECORDED RUN"`).
