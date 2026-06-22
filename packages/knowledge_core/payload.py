"""Recitation payload builder.

⚠️ DEPENDENCY NOTE (read before using):

The source `lines_payload(title, lines, intent, source)` in
/tmp/refsrc_canary.py returns a `RetrieveResponse` — a Pydantic/FastAPI model
defined in the server module. Per the refactor rules, anything that depends on
`RetrieveResponse` (a serving-layer type) does NOT belong in the pure
`knowledge_core`. The full `lines_payload` is therefore LEFT FOR THE SERVING
LAYER.

What lives here is only the pure, framework-free part: building the JSON
`context` string and the `intent`/`sources` dict — exactly the values the
source `lines_payload` passes into `RetrieveResponse(...)`. The serving layer can
do `RetrieveResponse(**build_lines_payload_dict(...))`.

Source (verbatim) for reference::

    def lines_payload(title, lines, intent, source):
        return RetrieveResponse(
            context=json.dumps(
                {"type": "full_recitation_lines", "title": title, "lines": lines},
                ensure_ascii=False,
            ),
            intent={**intent, "query_type": "recite_full_text", "title": title},
            sources=[source],
        )
"""
from __future__ import annotations

import json


def build_lines_payload_dict(title, lines, intent, source):
    """Pure helper: the exact field values the source `lines_payload` feeds into
    `RetrieveResponse`. No Pydantic/FastAPI dependency.

    The serving layer reconstitutes the response with::

        RetrieveResponse(**build_lines_payload_dict(title, lines, intent, source))
    """
    return {
        "context": json.dumps(
            {"type": "full_recitation_lines", "title": title, "lines": lines},
            ensure_ascii=False,
        ),
        "intent": {**intent, "query_type": "recite_full_text", "title": title},
        "sources": [source],
    }
