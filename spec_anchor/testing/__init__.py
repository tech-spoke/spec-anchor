"""Test support package for SPEC-anchor E2E test plan.

This package implements harness components consumed by ``tests/conftest.py``
to record verification evidence as defined in
``doc/e2eテスト/test_plan.ja.md``.
"""

from spec_anchor.testing.evidence import EvidenceCollector, SpecRef

__all__ = ["EvidenceCollector", "SpecRef"]
