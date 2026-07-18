"""Reproducible red-team studies built on the shipped runner + scoring (defensive, sim-only).

Each study REUSES ``provael.runner`` + ``provael.scoring`` (no ASR reimplementation) and keeps a
deterministic, GPU-free CPU-stub path so it runs in CI; real-model paths are gated behind
``PROVAEL_INTEGRATION=1`` + the relevant extra. The runnable entry points live under the top-level
``studies/`` directory and import the logic from here.
"""

from __future__ import annotations

__all__: list[str] = []
