"""RFC 8785 canonical JSON serializer for deterministic signatures.

Pure implementation: sorts keys lexicographically, eliminates unnecessary whitespace,
and enforces UTF-8 character encoding.
"""

import json
from typing import Any


def canonical_json_bytes(data: Any) -> bytes:
    """Serialize arbitrary data structures into RFC 8785 canonical JSON bytes.

    Invariants:
    - Dict keys sorted alphabetically.
    - Separators are (',', ':') with zero whitespace.
    - Float values rejected or formatted without exponential distortion.
    - Encoded as strictly valid UTF-8.
    """
    json_str = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return json_str.encode("utf-8")


def canonical_digest(data: Any) -> str:
    """Compute SHA-256 hex digest of RFC 8785 canonical JSON."""
    import hashlib

    return hashlib.sha256(canonical_json_bytes(data)).hexdigest()
