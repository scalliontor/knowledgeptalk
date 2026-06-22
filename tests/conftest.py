"""Make `knowledge_core` and `retrieval` importable regardless of pytest cwd.

Adds repo `packages/` to sys.path. No model, no DB — pure path wiring. Importing
`retrieval` here is safe: per its module docstrings it opens no connections and
loads no model at import time.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, ".."))
_PKGS = os.path.join(_REPO, "packages")

if _PKGS not in sys.path:
    sys.path.insert(0, _PKGS)
