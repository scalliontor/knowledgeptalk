"""Make `knowledge_core` and the local corpus/runner importable regardless of
the cwd pytest is invoked from. No model, no DB — pure path wiring."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", ".."))
_PKGS = os.path.join(_REPO, "packages")

for _p in (_PKGS, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
