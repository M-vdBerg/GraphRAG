"""Typed dataclasses mirroring the AGE graph vertex/edge structure."""

from dataclasses import dataclass


@dataclass
class DocumentNode:
    doc_id: str
    file_path: str
    file_name: str
    title: str | None
    updated_at: str  # ISO-8601


@dataclass
class ChunkNode:
    chunk_id: str
    doc_id: str
    heading: str | None
    position: int
    content: str
    token_count: int | None


@dataclass
class EntityNode:
    entity_id: str   # sha256(normalized|type)
    name: str
    type: str        # PERSON | ORG | LOCATION | SYSTEM | TECHNOLOGY | CONCEPT
    normalized: str  # lowercase, singular
