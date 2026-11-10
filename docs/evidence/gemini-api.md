# Gemini API Specification & Model Verification

**Documentation Reference & Verification Date**:
- **Date Verified**: 10 November 2026
- **Official Documentation URLs**:
  - Models Overview: https://ai.google.dev/gemini-api/docs/models/gemini
  - Generate Content API Reference: https://ai.google.dev/api/generate-content
  - Structured Outputs / JSON Mode: https://ai.google.dev/gemini-api/docs/json-mode

## Model Configuration & Endpoints
- **Endpoint**: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- **Default Verified Model**: `gemini-2.5-flash` (high-speed multimodal reasoning model)
- **Environment Variable Overrides**:
  - `GEMINI_API_KEY`: API key for Google Generative AI (stored strictly server-side in environment, never exposed to client/browser or logs).
  - `GEMINI_MODEL`: Model identifier (defaults to `gemini-2.5-flash`).
- **Generation Parameters**:
  - `temperature`: `0.0` (deterministic extraction)
  - `maxOutputTokens`: `1024` (token ceiling)
  - `responseMimeType`: `"application/json"` (strict JSON mode)
  - `timeout`: 10.0 seconds
  - `retries`: 1 retry on network/5xx server errors
- **Daily Rate Limiting**:
  - 100 calls/day demo cap enforced in-memory to prevent unexpected quota exhaustion.
  - When cap is reached, returns HTTP 429 / `"demo budget reached"`.

