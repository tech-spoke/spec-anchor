"""Graph extraction schema and provenance helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from llama_index.core.indices.property_graph import SchemaLLMPathExtractor
from llama_index.core.llms import LLM
from pydantic import Field

from spec_grag.protocol import StrictModel


Entities = Literal["DOCUMENT", "CHAPTER", "SECTION", "ANCHOR"]
Relations = Literal[
    "CONTAINS",
    "MENTIONS",
    "RELATED_TO",
    "DEPENDS_ON",
    "REFINES",
    "CONTRASTS_WITH",
]

KG_VALIDATION_SCHEMA: list[tuple[str, str, str]] = [
    ("DOCUMENT", "CONTAINS", "CHAPTER"),
    ("CHAPTER", "CONTAINS", "SECTION"),
    ("CHAPTER", "MENTIONS", "ANCHOR"),
    ("SECTION", "MENTIONS", "ANCHOR"),
    ("CHAPTER", "RELATED_TO", "CHAPTER"),
    ("CHAPTER", "DEPENDS_ON", "CHAPTER"),
    ("CHAPTER", "REFINES", "CHAPTER"),
    ("CHAPTER", "CONTRASTS_WITH", "CHAPTER"),
    ("ANCHOR", "RELATED_TO", "ANCHOR"),
    ("ANCHOR", "DEPENDS_ON", "ANCHOR"),
    ("ANCHOR", "REFINES", "ANCHOR"),
    ("ANCHOR", "CONTRASTS_WITH", "ANCHOR"),
]

SPEC_GRAG_EXTRACT_PROMPT = """\
あなたは仕様書から軽量な関係グラフ候補を抽出する。

制約:
- entity type は DOCUMENT / CHAPTER / SECTION / ANCHOR のみ。
- relation type は CONTAINS / MENTIONS / RELATED_TO / DEPENDS_ON / REFINES / CONTRASTS_WITH のみ。
- DOCUMENT / CHAPTER / SECTION は、入力 metadata の current_section_id / heading_path / doc_path を優先し、自由に別 ID を作らない。
- 主な抽出対象は ANCHOR と、current section を source とする関係候補。
- 判断できない target は無理に既存章へ結びつけず、properties.target_hint に自由文字列を残す。
- 最大 {max_triplets_per_chunk} triplets。

本文:
{text}
"""


class ExtractionProvenance(StrictModel):
    source_document_id: str
    source_chapter_id: str
    source_section_id: str
    source_chunk_id: str
    source_hash: str
    extract_run_id: str
    extractor_name: str
    extractor_version: str
    extracted_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_metadata(self) -> dict[str, str]:
        return self.model_dump(mode="json")


def make_schema_llm_path_extractor(
    llm: LLM,
    *,
    max_triplets_per_chunk: int = 20,
    num_workers: int = 4,
) -> SchemaLLMPathExtractor:
    return SchemaLLMPathExtractor(
        llm=llm,
        extract_prompt=SPEC_GRAG_EXTRACT_PROMPT,
        possible_entities=Entities,
        possible_relations=Relations,
        kg_validation_schema=KG_VALIDATION_SCHEMA,
        strict=True,
        max_triplets_per_chunk=max_triplets_per_chunk,
        num_workers=num_workers,
        allow_additional_properties=True,
    )
