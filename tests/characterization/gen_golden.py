"""Regenerate the golden snapshot for knowledge_core characterization.

Run this ONLY when an intentional behavior change has been reviewed and approved
(the whole point is that the golden file should NOT move during a
behavior-preserving refactor). It writes `golden_knowledge_core.json` next to
this script.

    python3 tests/characterization/gen_golden.py
"""
from __future__ import annotations

import json
import os

from corpus import build_corpus
from runner import compute_record

_HERE = os.path.dirname(os.path.abspath(__file__))
_GOLDEN = os.path.join(_HERE, "golden_knowledge_core.json")


def main() -> None:
    corpus = build_corpus()
    records = [compute_record(c["query"], c["profile"]) for c in corpus]
    payload = {
        "schema": 1,
        "n": len(records),
        "records": records,
    }
    with open(_GOLDEN, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, sort_keys=True)
        fh.write("\n")
    print("wrote %d records -> %s" % (len(records), _GOLDEN))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, _HERE)
    main()
