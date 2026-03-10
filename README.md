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
  │  Document vertices, Chunk vertices
  │  HAS_CHUNK / NEXT_CHUNK / LINKS_TO edges
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
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` | HuggingFace model ID |
| `EMBEDDING_DEVICE` | `cuda` | `cuda` or `cpu` |
| `MCP_PORT` | `8000` | MCP server port |

## Embedding model

Default: **`BAAI/bge-large-en-v1.5`** (1024-dim, asymmetric retrieval).
Optimised for H100/H200/RTX 6000 Ada GPU hardware.

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
