"""Readers for external recorded-robot datasets.

Kept separate from `suites/` on purpose: a suite SIMULATES and can be stepped, while everything
here is a fixed recording that can only be replayed. Conflating the two is how an open-loop replay
starts getting described as a rollout.
"""
