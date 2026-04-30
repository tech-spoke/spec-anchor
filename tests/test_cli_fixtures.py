from __future__ import annotations

import json
from pathlib import Path

from spec_grag.protocol import SlashCommandRequest


def test_cli_request_fixtures_match_transport_schema() -> None:
    fixture_dir = Path(__file__).parent / "fixtures/cli"
    for path in sorted(fixture_dir.glob("*.request.json")):
        payload = json.loads(
            path.read_text(encoding="utf-8").replace("__PROJECT_ROOT__", "/tmp/spec-grag")
        )
        request = SlashCommandRequest.model_validate(payload)
        assert request.project_root == "/tmp/spec-grag"
