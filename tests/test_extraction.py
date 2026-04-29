from __future__ import annotations

from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata

from spec_grag.extraction import (
    ExtractionProvenance,
    KG_VALIDATION_SCHEMA,
    make_schema_llm_path_extractor,
)


class DummyLLM(CustomLLM):
    @property
    def metadata(self) -> LLMMetadata:
        return LLMMetadata(model_name="dummy")

    def complete(self, prompt: str, formatted: bool = False, **kwargs):
        return CompletionResponse(text='{"triplets": []}')

    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs):
        yield self.complete(prompt, formatted=formatted, **kwargs)


def test_make_schema_llm_path_extractor_uses_light_schema() -> None:
    extractor = make_schema_llm_path_extractor(DummyLLM(), max_triplets_per_chunk=7)

    assert extractor.strict is True
    assert extractor.max_triplets_per_chunk == 7
    assert extractor.kg_validation_schema["relationships"] == KG_VALIDATION_SCHEMA


def test_extraction_provenance_to_metadata() -> None:
    provenance = ExtractionProvenance(
        source_document_id="docs/spec/auth.md",
        source_chapter_id="docs/spec/auth.md#auth",
        source_section_id="docs/spec/auth.md#auth-login",
        source_chunk_id="chunk-1",
        source_hash="abc",
        extract_run_id="run-1",
        extractor_name="SchemaLLMPathExtractor",
        extractor_version="prompt-v1",
        extracted_at="2026-04-29T00:00:00+00:00",
    )

    metadata = provenance.to_metadata()

    assert metadata["source_section_id"] == "docs/spec/auth.md#auth-login"
    assert metadata["extract_run_id"] == "run-1"
