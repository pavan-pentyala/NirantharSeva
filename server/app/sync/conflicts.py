"""Stub for Phase 1.1.

The toy model resolves concurrent writes inline in push.py: highest
(lamport, device_id) wins the LWW register, ties broken by device_id. That
is enough to make the property test's permutation-invariance hold, but it
is not the real conflict decision table.

The real table — the five-row decision matrix per plan §6.3, `conflict`
status, `sync_conflict` records — arrives in Phase 2 for the referral
domain. This module is the marker for where that logic will live.
"""
