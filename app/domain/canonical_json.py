"""RFC 8785 canonical JSON serializer for deterministic signatures.

Uses the official rfc8785 package (JSON Canonicalization Scheme / JCS).
Invariants:
- Dict keys sorted lexicographically by UTF-16 code units (RFC 8785 Section 3.2.3).
- Zero whitespace between elements (separators are ',', ':').
- Floats formatted according to ECMAScript standard specification.
- Output encoded strictly as UTF-8 bytes.
"""

import hashlib
from typing import Any

import rfc8785


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize arbitrary Python data structures into RFC 8785 canonical JSON bytes."""
    return rfc8785.dumps(data)


def canonical_digest(data: Any) -> str:
    """Compute SHA-256 hex digest of RFC 8785 canonical JSON."""
    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()
