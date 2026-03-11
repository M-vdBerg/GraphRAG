# GraphRAG

A graph-based Retrieval-Augmented Generation system powered by **PostgreSQL + Apache AGE** with an **MCP server** interface.

Drop markdown files into a watched folder — the system automatically parses, embeds, and indexes them as a knowledge graph. Query the graph through the MCP server from any MCP-compatible client (Claude Desktop, Claude Code, etc.).

## Architecture

```
docs/  ←── you edit markdown here
  │
  ▼
[watcher service]
  │  watchdog file events
  │  sentence-transformers (CUDA) embeddings
  │  Markdown → chunks → vectors
  ▼
[PostgreSQL + AGE + pgvector]
  │  Document / Chunk / Entity vertices
  │  HAS_CHUNK / NEXT_CHUNK / LINKS_TO edges  (structural, automatic)
  │  SIMILAR_TO / MENTIONS edges              (semantic, via enricher)
  │  vector(1024) cosine similarity index
  ▼
[MCP server — HTTP/SSE]
  tools: search · get_document · list_documents · get_related · get_chunk_context
```

## Quick start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — at minimum set POSTGRES_PASSWORD

# 2. (Optional) copy the dev override for bind-mounted docs folder
cp docker-compose.override.yml.example docker-compose.override.yml

# 3. Start everything
docker compose up --build

# 4. Drop markdown files into docs/
cp my-notes.md docs/
# The watcher picks them up within seconds
```

## Semantic enrichment (optional)

The **enricher** adds two layers of cross-document connections that the watcher doesn't create automatically:

| Layer | What it does | LLM needed? |
|---|---|---|
| `SIMILAR_TO` edges | Links semantically similar chunks across documents using pgvector cosine similarity | No |
| `MENTIONS` edges + `Entity` vertices | Extracts named entities and concepts from each chunk | Yes |

Run it on demand (after documents are indexed):

```bash
docker compose exec watcher python -m graphrag.enricher
```

The enricher is **incremental** — it only processes chunks that are new or whose content changed since the last run. Switching `ENRICHER_MODEL` triggers a full re-run for the new model.

### LLM endpoint

The enricher works with any OpenAI-compatible inference server. Configure in `.env`:

```bash
ENRICHER_BASE_URL=http://localhost:4000/v1   # LiteLLM, vLLM, Ollama, LM Studio, …
ENRICHER_API_KEY=dummy
ENRICHER_MODEL=mistral/mistral-small-24b     # or any model your endpoint serves
```

Recommended models (instruction-following + structured JSON output):
- `mistral/mistral-small-24b` — fast, accurate for entity extraction
- `qwen/qwen2.5-72b-instruct` — higher quality at the cost of throughput

## MCP tools

| Tool | Description |
|---|---|
| `search` | Semantic vector search — returns ranked chunks with scores |
| `get_document` | Retrieve all chunks of a document by `doc_id` |
| `list_documents` | List all indexed documents |
| `get_related` | Graph traversal — documents linked via markdown hyperlinks |
| `get_chunk_context` | Expand context around a search hit (neighboring chunks) |

## Connecting to Claude Desktop / Claude Code

Add to your MCP config (`claude_desktop_config.json` or `.claude/mcp.json`):

```json
{
  "mcpServers": {
    "graphrag": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

## Environment variables

See [`.env.example`](.env.example) for the full list.
Key variables:

| Variable | Default | Description |
|---|---|---|
| `POSTGRES_PASSWORD` | *(required)* | PostgreSQL password |
| `EMBEDDING_MODEL` | `BAAI/bge-m3` | HuggingFace model ID |
| `EMBEDDING_DEVICE` | `cuda` | `cuda` or `cpu` |
| `MCP_PORT` | `8000` | MCP server port |
| `ENRICHER_BASE_URL` | `http://localhost:4000/v1` | OpenAI-compatible inference endpoint |
| `ENRICHER_MODEL` | `mistral/mistral-small-24b` | Model for entity extraction |
| `SIMILAR_TO_THRESHOLD` | `0.82` | Cosine similarity cutoff for SIMILAR_TO edges |

## Graph schema

### Vertex labels
| Label | Description |
|---|---|
| `Document` | One vertex per indexed markdown file |
| `Chunk` | One vertex per heading section within a document |
| `Entity` | Named entity or concept extracted by the enricher |

### Edge labels
| Label | From → To | Created by | Description |
|---|---|---|---|
| `HAS_CHUNK` | Document → Chunk | watcher | Document owns chunk |
| `NEXT_CHUNK` | Chunk → Chunk | watcher | Sequential order within document |
| `LINKS_TO` | Document → Document | watcher | Explicit markdown hyperlinks |
| `SIMILAR_TO` | Chunk ↔ Chunk | enricher | Semantic similarity above threshold |
| `MENTIONS` | Chunk → Entity | enricher | Chunk mentions this entity/concept |

## Embedding model

Default: **`BAAI/bge-m3`** (1024-dim, multilingual, 100+ languages including German).

If you change `EMBEDDING_MODEL` to a model with different output dimensions, update `vector(1024)` in `docker/postgres/init/02_schema.sql` accordingly and recreate the database volume.

## Pre-built images (GHCR)

Images are published to GitHub Container Registry on every push to `main`:

```
ghcr.io/<owner>/graphrag-postgres:<tag>
ghcr.io/<owner>/graphrag-watcher:<tag>
ghcr.io/<owner>/graphrag-mcp:<tag>
```

Set `GITHUB_REPOSITORY=<owner>/GraphRAG` in your `.env`.

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
