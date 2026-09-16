"""Small helpers shared by the agent tool adapters."""

from __future__ import annotations

import json
from typing import Any


def to_json(payload: Any) -> str:
    """Serialize a tool result for the model.

    Chinese text stays unescaped and the payload is indented, matching the
    formatting the adapters applied inline before they were extracted.
    """
    return json.dumps(payload, ensure_ascii=False, indent=2)
