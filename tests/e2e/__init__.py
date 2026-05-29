"""End-to-end verification for the user-facing output of slash commands.

This package backs the課題 ``doc/TODO/TODO_slash_command_user_facing_output.ja.md``.
The slash commands (`/spec-core` / `/spec-inject` / `/spec-realign`) format the
internal CLI JSON into a human-facing reply. These tests guard that contract by:

* enforcing that the Agent-formatted final replies stored under ``snapshots/``
  never leak the internal field names / enum values / pipeline stage names
  (see :mod:`tests.e2e.forbidden_terms`), and
* enforcing that each registered scenario's snapshot contains the required
  human-facing content (see :mod:`tests.e2e.scenarios`).

The snapshot ``.md`` files are the evidence artifacts that a human reviews; the
pytest assertions are the machine gate that keeps the contract from regressing.
"""
