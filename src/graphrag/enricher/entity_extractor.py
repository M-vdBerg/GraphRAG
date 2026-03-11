"""LLM-based entity and concept extraction via an OpenAI-compatible endpoint.

Works with any OpenAI-compatible inference server:
  LiteLLM proxy, vLLM, Ollama (with --api openai), LM Studio, etc.

The extractor is stateless — instantiate once and call extract() per chunk.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

ENTITY_TYPES = {"PERSON", "ORG", "LOCATION", "SYSTEM", "TECHNOLOGY", "CONCEPT"}

_SYSTEM_PROMPT = """\
You are an expert at structured information extraction.
Extract entities and topics from text chunks and return ONLY valid JSON.
Do not explain or add any text outside the JSON object.\
"""

_USER_TEMPLATE = """\
Extract from the following text chunk:
---
{content}
---

Return ONLY this JSON structure (no markdown fences, no explanation):
{{
  "entities": [
    {{"name": "ExactName", "type": "PERSON|ORG|LOCATION|SYSTEM|TECHNOLOGY|CONCEPT", "normalized": "lowercase singular"}}
  ],
  "topics": ["short topic phrase"]
}}

Rules:
- Maximum 10 entities, maximum 3 topics
- Only extract clearly stated items, not implied ones
- normalized: lowercase, singular, no special characters
- Skip generic terms like "user", "system", "data" unless highly specific\
"""


@dataclass
class ExtractionResult:
    entities: list[dict]   # [{name, type, normalized}]
    topics: list[str]


class EntityExtractor:
    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    async def extract(self, content: str) -> ExtractionResult:
        """Extract entities and topics from a single chunk of text."""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _USER_TEMPLATE.format(content=content)},
                ],
                temperature=0.0,
                max_tokens=512,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or "{}"
        except Exception:
            logger.warning("LLM call failed for chunk (len=%d), skipping", len(content))
            return ExtractionResult(entities=[], topics=[])

        return _parse_response(raw)


def _parse_response(raw: str) -> ExtractionResult:
    """Parse and validate the LLM JSON response, tolerating minor format issues."""
    # Strip accidental markdown fences some models emit despite instructions
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Could not parse LLM response as JSON: %.200s", raw)
        return ExtractionResult(entities=[], topics=[])

    entities: list[dict] = []
    for item in data.get("entities", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        etype = str(item.get("type", "CONCEPT")).upper().strip()
        normalized = str(item.get("normalized", name.lower())).strip()
        if not name:
            continue
        if etype not in ENTITY_TYPES:
            etype = "CONCEPT"
        entities.append({"name": name, "type": etype, "normalized": normalized})

    topics: list[str] = [
        str(t).strip()
        for t in data.get("topics", [])
        if isinstance(t, str) and t.strip()
    ]

    return ExtractionResult(entities=entities[:10], topics=topics[:3])
