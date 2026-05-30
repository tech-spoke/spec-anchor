from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spec_anchor.llm_provider import (
    FakeLlmProvider,
    GenerationCache,
    LlmRequest,
    RealLlmProviderDisabledError,
    SubprocessLlmProvider,
    build_spec_core_llm_provider,
    generate_with_cache,
    generate_with_retries,
    select_llm_provider_config,
    summarize_generation_results,
)


def _value(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value[key]
    return getattr(value, key)


def _diagnostic(result: object, index: int = -1) -> Any:
    diagnostics = _value(result, "diagnostics")
    assert diagnostics
    diagnostic = diagnostics[index]
    assert not isinstance(
        diagnostic,
        str,
    ), "diagnostics must be structured objects, not free-form strings"
    return diagnostic


def _request(
    source_hash: str = "hash-a",
    prompt_version: str = "p1",
    model: str = "fake-model",
    semantic_hash: str | None = "semantic-a",
) -> LlmRequest:
    return LlmRequest(
        task="section_metadata",
        prompt="summarize this section",
        prompt_version=prompt_version,
        model=model,
        source_hash=source_hash,
        semantic_hash=semantic_hash,
        section_id="section-a",
    )


def test_t_u26_fake_provider_returns_deterministic_structured_response() -> None:
    provider = FakeLlmProvider({"summary": "S", "search_keys": ["k"]})

    result = generate_with_retries(
        provider,
        _request(),
        required_fields=("summary", "search_keys"),
    )

    assert result.status == "success"
    assert result.artifact is not None
    assert result.artifact.output == {"summary": "S", "search_keys": ["k"]}
    assert result.artifact.prompt_version == "p1"
    assert result.artifact.model == "fake-model"
    assert result.artifact.source_hash == "hash-a"
    assert provider.calls == 1

    repeated = generate_with_retries(
        provider,
        _request(),
        required_fields=("summary", "search_keys"),
    )

    assert repeated.status == "success"
    assert repeated.artifact is not None
    assert repeated.artifact.output == result.artifact.output
    assert provider.calls == 2


def test_t_u26_schema_violation_returns_structured_failure_diagnostics() -> None:
    provider = FakeLlmProvider(mode="invalid")

    result = generate_with_retries(
        provider,
        _request(),
        required_fields=("summary", "search_keys"),
        max_retries=1,
    )

    assert result.status == "failed"
    assert result.attempts == 2
    diagnostic = _diagnostic(result)
    assert _value(diagnostic, "reason_code") == "validation_error"
    assert _value(diagnostic, "attempt") == 2
    assert _value(diagnostic, "stage") == "section_metadata"
    assert _value(diagnostic, "model") == "fake-model"
    assert _value(diagnostic, "timeout_sec") == 120
    assert provider.calls == 2


def test_t_u26_timeout_returns_structured_failure_diagnostics() -> None:
    provider = FakeLlmProvider(mode="timeout")

    result = generate_with_retries(
        provider,
        _request(),
        required_fields=("summary",),
        timeout_sec=1,
        max_retries=0,
    )

    assert result.status == "failed"
    diagnostic = _diagnostic(result, 0)
    assert _value(diagnostic, "reason_code") == "timeout"
    assert _value(diagnostic, "attempt") == 1
    assert _value(diagnostic, "stage") == "section_metadata"
    assert _value(diagnostic, "model") == "fake-model"
    assert _value(diagnostic, "timeout_sec") == 1


@pytest.mark.parametrize("command", (["codex"], ["claude"]))
def test_t_u26_real_provider_can_be_explicitly_disabled_by_tests(
    monkeypatch: pytest.MonkeyPatch,
    command: list[str],
) -> None:
    called = False

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess([], 0, stdout="{}", stderr="")

    monkeypatch.setattr("spec_anchor.llm_provider.subprocess.run", fake_run)
    provider = SubprocessLlmProvider(command, real_smoke_enabled=False)

    with pytest.raises(RealLlmProviderDisabledError):
        provider.generate(_request(), timeout_sec=1)

    assert called is False


def test_t_u26_configured_real_provider_is_enabled_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from spec_anchor.llm_provider import build_spec_core_llm_provider

    monkeypatch.delenv("SPEC_ANCHOR_FAKE_LLM", raising=False)
    provider = build_spec_core_llm_provider(
        {
            "providers": {
                "codex": {
                    "command": "codex",
                    "model": "real-smoke",
                    "effort": "low",
                },
            },
        }
    )

    assert getattr(provider, "provider_id") == "codex"
    assert getattr(provider, "real_provider_enabled") is True


def test_t_u26_codex_provider_uses_noninteractive_exec(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        command = list(args[0])
        calls.append({"command": command, "kwargs": kwargs})
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="\n".join(
                [
                    json.dumps({"type": "message", "delta": "working"}),
                    json.dumps(
                        {
                            "type": "done",
                            "result": json.dumps(
                                {"summary": "S", "search_keys": ["k"]},
                                ensure_ascii=False,
                            ),
                        },
                        ensure_ascii=False,
                    ),
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr("spec_anchor.llm_provider.subprocess.run", fake_run)
    provider = SubprocessLlmProvider(["codex"], real_smoke_enabled=True)

    output = provider.generate(_request(model="gpt-test", semantic_hash=None), timeout_sec=3)

    assert output == {"summary": "S", "search_keys": ["k"]}
    command = calls[0]["command"]
    assert command[:4] == ["codex", "--ask-for-approval", "never", "exec"]
    assert command[-1] == "-"
    assert "--json" in command
    assert "--output-schema" in command
    assert calls[0]["kwargs"]["input"].startswith("You are the SPEC-anchor /spec-core")
    assert "CODEX_HOME" not in calls[0]["kwargs"]["env"]
    assert "CODEX_THREAD_ID" not in calls[0]["kwargs"]["env"]


def test_t_u26_codex_provider_uses_batch_sections_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        command = list(args[0])
        schema_path = Path(command[command.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text())
        calls.append({"command": command, "schema": schema, "kwargs": kwargs})
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="\n".join(
                [
                    json.dumps(
                        {
                            "type": "done",
                            "result": json.dumps(
                                {
                                    "sections": [
                                        {
                                            "section_id": "a",
                                            "summary": "A",
                                            "search_keys": ["ka"],
                                        },
                                        {
                                            "section_id": "b",
                                            "summary": "B",
                                            "search_keys": ["kb"],
                                        },
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        },
                        ensure_ascii=False,
                    )
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr("spec_anchor.llm_provider.subprocess.run", fake_run)
    provider = SubprocessLlmProvider(["codex"], real_smoke_enabled=True)
    request = LlmRequest(
        task="section_metadata",
        stage="section_metadata",
        prompt="batch",
        prompt_version="p1",
        model="gpt-test",
        source_hash="batch-hash",
        section_hashes={"a": "ha", "b": "hb"},
    )

    output = provider.generate(request, timeout_sec=3)

    assert output["sections"][0]["section_id"] == "a"
    assert calls[0]["schema"]["required"] == ["sections"]
    assert '"sections"' in calls[0]["kwargs"]["input"]


def test_related_section_selection_prompt_matches_sections_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        command = list(args[0])
        schema_path = Path(command[command.index("--output-schema") + 1])
        schema = json.loads(schema_path.read_text())
        calls.append({"schema": schema, "kwargs": kwargs})
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="\n".join(
                [
                    json.dumps(
                        {
                            "type": "done",
                            "result": json.dumps(
                                {
                                    "sections": [
                                        {
                                            "source_section_id": "docs/spec/a.md#a",
                                            "related_sections": [],
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            ),
                        },
                        ensure_ascii=False,
                    )
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr("spec_anchor.llm_provider.subprocess.run", fake_run)
    provider = SubprocessLlmProvider(["codex"], real_smoke_enabled=True)
    request = LlmRequest(
        task="related_section_selection",
        stage="related_section_selection",
        prompt="{}",
        prompt_version="related-sections-v1",
        model="gpt-test",
        source_hash="related-hash",
        section_hashes={"docs/spec/a.md#a": "ha"},
    )

    output = provider.generate(request, timeout_sec=3)

    prompt = calls[0]["kwargs"]["input"]
    assert output == {
        "sections": [
            {
                "source_section_id": "docs/spec/a.md#a",
                "related_sections": [],
            }
        ]
    }
    assert calls[0]["schema"]["required"] == ["sections"]
    assert 'array field "sections"' in prompt
    assert 'array field "related_sections"' in prompt
    assert 'array field "related_sections". Each item' not in prompt
    related_item_schema = calls[0]["schema"]["properties"]["sections"]["items"][
        "properties"
    ]["related_sections"]["items"]
    assert "reason" not in related_item_schema["required"]
    assert "channels" not in related_item_schema["required"]


def test_t_u26_claude_provider_uses_print_and_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        command = list(args[0])
        calls.append({"command": command, "kwargs": kwargs})
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {"structured_output": {"summary": "S", "search_keys": ["k"]}},
                ensure_ascii=False,
            ),
            stderr="",
        )

    monkeypatch.setattr("spec_anchor.llm_provider.subprocess.run", fake_run)
    provider = SubprocessLlmProvider(["claude"], real_smoke_enabled=True)

    output = provider.generate(_request(model="real-smoke"), timeout_sec=3)

    assert output == {"summary": "S", "search_keys": ["k"]}
    command = calls[0]["command"]
    assert command[:3] == ["claude", "--print", "--effort"]
    assert "--no-session-persistence" in command
    assert "--disable-slash-commands" in command
    assert "--output-format" in command
    assert "--json-schema" in command
    assert calls[0]["kwargs"]["input"] is None


@pytest.mark.external
def test_t_u26_real_provider_uses_configured_agent_cli() -> None:
    command_name = "codex"
    executable = shutil.which(command_name)
    if executable is None:
        pytest.skip(f"{command_name} is not installed on PATH")

    provider = SubprocessLlmProvider([executable], real_smoke_enabled=True)
    result = generate_with_retries(
        provider,
        _request(model="real-smoke"),
        required_fields=("summary", "search_keys"),
        timeout_sec=120,
        max_retries=0,
    )

    assert result.status == "success"
    assert result.artifact is not None


def test_t_i16_generation_cache_hits_when_only_semantic_hash_changes(
    tmp_path: Path,
) -> None:
    cache = GenerationCache(tmp_path)
    provider = FakeLlmProvider({"summary": "S", "search_keys": ["k"]})
    request = _request()
    same_contract_request = _request(semantic_hash="semantic-b")

    first, first_cached = generate_with_cache(
        provider,
        request,
        cache=cache,
        required_fields=("summary", "search_keys"),
    )
    second, second_cached = generate_with_cache(
        provider,
        same_contract_request,
        cache=cache,
        required_fields=("summary", "search_keys"),
    )

    assert first.status == "success"
    assert first_cached is False
    assert second.status == "success"
    assert second_cached is True
    assert provider.calls == 1


def test_t_i16_generation_cache_misses_on_source_hash_or_prompt_version_change(
    tmp_path: Path,
) -> None:
    cache = GenerationCache(tmp_path)
    provider = FakeLlmProvider({"summary": "S", "search_keys": ["k"]})

    for request in (
        _request(source_hash="hash-a", prompt_version="p1"),
        _request(source_hash="hash-b", prompt_version="p1"),
        _request(source_hash="hash-b", prompt_version="p2"),
    ):
        result, cached = generate_with_cache(
            provider,
            request,
            cache=cache,
            required_fields=("summary", "search_keys"),
        )
        assert result.status == "success"
        assert cached is False

    assert provider.calls == 3


def test_t_i16_generation_cache_misses_on_model_change(tmp_path: Path) -> None:
    cache = GenerationCache(tmp_path)
    provider = FakeLlmProvider({"summary": "S", "search_keys": ["k"]})

    for request in (
        _request(model="fake-model-a"),
        _request(model="fake-model-b"),
    ):
        result, cached = generate_with_cache(
            provider,
            request,
            cache=cache,
            required_fields=("summary", "search_keys"),
        )
        assert result.status == "success"
        assert cached is False

    assert provider.calls == 2


def test_t_u26_llm_config_scope_is_spec_core_only() -> None:
    import spec_anchor.llm_provider as llm_provider

    validate_scope = getattr(llm_provider, "validate_llm_usage_scope", None)
    assert callable(
        validate_scope
    ), "spec_anchor.llm_provider.validate_llm_usage_scope(scope) is required"

    assert validate_scope("/spec-core") == "/spec-core"
    for agent_scope in ("/spec-inject", "/spec-realign", "agent"):
        with pytest.raises(Exception) as exc_info:
            validate_scope(agent_scope)
        message = str(exc_info.value)
        assert "[llm]" in message
        assert "/spec-core" in message
        assert "Agent" in message


def test_t_u26_multi_llm_config_selects_explicit_agent_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPEC_ANCHOR_FAKE_LLM", raising=False)
    config = {
        "providers": {
            "codex": {
                "command": "codex",
                "model": "gpt-5.4-mini",
            },
            "claude": {"command": "claude"},
        },
    }

    selected = select_llm_provider_config(config, provider_id="claude")
    provider = build_spec_core_llm_provider(
        config,
        provider_id="claude",
        real_smoke_enabled=True,
    )

    assert selected["command"] == "claude"
    assert getattr(provider, "provider_id") == "claude"
    assert getattr(provider, "command") == ["claude"]


def test_t_u26_multi_llm_config_falls_back_to_first_provider() -> None:
    config = {
        "providers": {
            "codex": {"command": "codex"},
            "claude": {"command": "claude"},
        },
    }

    # No CLI / stage_routing -> first defined provider (codex).
    assert select_llm_provider_config(config)["command"] == "codex"
    # Explicit provider_id (CLI --llm-provider) selects the named provider.
    assert select_llm_provider_config(config, provider_id="claude")["command"] == "claude"
    # Unknown provider id raises.
    with pytest.raises(Exception) as exc_info:
        select_llm_provider_config(config, provider_id="missing")
    assert "configured providers" in str(exc_info.value)


def test_t_u26_max_retries_is_additional_attempt_count() -> None:
    provider = FakeLlmProvider(mode="invalid")

    result = generate_with_retries(
        provider,
        _request(),
        required_fields=("summary",),
        max_retries=1,
    )

    assert result.status == "failed"
    assert provider.calls == 2
    assert result.attempts == 2


def test_t_i07_partial_llm_failure_folds_to_failed_like_total_failure() -> None:
    success = generate_with_retries(
        FakeLlmProvider({"summary": "S"}),
        _request(),
        required_fields=("summary",),
    )
    failure = generate_with_retries(
        FakeLlmProvider(mode="invalid"),
        _request(),
        required_fields=("summary",),
        max_retries=0,
    )

    partial = summarize_generation_results({"a": success, "b": failure})
    total = summarize_generation_results({"a": failure, "b": failure})

    assert partial["freshness_status"] == "failed"
    assert partial["failed_sections"] == ["b"]
    assert partial["warnings"]
    assert partial["blocking_reasons"] == ["failed_required_artifact"]
    assert total["freshness_status"] == "failed"
