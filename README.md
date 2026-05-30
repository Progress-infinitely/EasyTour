# EasyTour

A vertical-domain RAG system for tourism knowledge Q&A. Supports document ingestion with automatic metadata extraction, multi-intent query routing, hybrid retrieval (dense + sparse), structured answer generation, and citation tracing.

## Architecture

### Document Import Pipeline

```
Upload PDF / Markdown
    ↓
PDF → Markdown (MinerU VLM)
    ↓
LLM Metadata Extraction (content type, region, entity names, chunk-level fields)
    ↓
Deduplication (SHA-256 content hash)
    ↓
Embedding → Milvus
```

### Query Pipeline

```
User Question
    ↓
Dual Intent Detection (retrieval_type + answer_intent)
    ↓
Alias Resolution (alias → canonical name)
    ↓
Hybrid Retrieval (Milvus dense + sparse)
    ↓
Web Search Augmentation (MCP, optional)
    ↓
Reranking → Answer Generation → SSE Stream
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python · FastAPI (async) · SSE streaming |
| Orchestration | LangGraph · LangChain |
| Vector DB | Milvus 2.4+ (dense COSINE + sparse IP hybrid search) |
| Document Storage | MongoDB (chat history, retrieval traces, document metadata, alias dictionary) |
| Object Storage | MinIO (raw file archival) |
| LLM / Embedding / Rerank | DashScope (Qwen) via OpenAI-compatible API |
| PDF Parsing | MinerU (VLM mode) |
| Frontend | Static HTML (import + chat pages) |

## Key Features

- **Deduplication-aware import**: SHA-256 content hash prevents re-processing identical documents. Supports three modes: skip (default), metadata-only update, and full reindex with rollback protection.
- **Dual intent routing**: Classifies queries by content type (attraction / route / hotel / food / transport / culture) and task intent (lookup / recommendation / planning / comparison / howto / generic), returning structured answers with appropriate templates.
- **Alias resolution**: Automatically normalizes colloquial names (e.g., abbreviations, alternate spellings) to canonical entity names via a learned alias dictionary.
- **Citation tracing**: Every answer includes source document labels for traceability.
- **Extensive test suite**: Unit tests for utilities, import nodes, and services; integration tests for end-to-end upload/query/dedup/citation flows.

## Project Structure

```
EasyTour/
├── easytour/
│   ├── api/
│   │   ├── routers/          # FastAPI route handlers (upload, query, metadata, documents, history)
│   │   └── main.py           # App factory, static file mounting
│   ├── core/                 # Config, dependency injection
│   ├── processor/
│   │   ├── import_process/   # LangGraph import pipeline nodes
│   │   └── query_process/    # LangGraph query pipeline nodes
│   ├── prompts/              # LLM prompt templates
│   ├── schema/               # Pydantic request/response models
│   ├── services/             # Business logic (document, trace, query)
│   ├── utils/                # Provider factory, clients, helpers
│   └── front/                # Static HTML pages (chat, import)
├── tests/                    # Unit + integration tests
├── .env.example              # Environment variable template
└── requirements.txt
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env — set OPENAI_API_KEY (or DASHSCOPE_API_KEY), MONGO_URL, etc.

# 3. Start service
python -m uvicorn easytour.api.main:app --host 0.0.0.0 --port 8000 --reload
```

- Document import: `http://localhost:8000/import.html`
- Chat interface: `http://localhost:8000/chat.html`
- Health check: `http://localhost:8000/healthz`
- API docs: `http://localhost:8000/docs`

## API Reference

### Query

| Endpoint | Method | Description |
|---|---|---|
| `/query` | POST | Submit a question, returns task_id |
| `/stream/{task_id}` | GET | SSE stream for query progress and results |
| `/status/{task_id}` | GET | Task status check |

### Document Import

| Endpoint | Method | Description |
|---|---|---|
| `/upload` | POST | Upload PDF/Markdown with optional overrides (`content_type`, `region`, `source_path`, `document_title`, `source_label_display`) |
| `/documents/{id}` | GET | Query document import metadata |
| `/documents/{id}/preview` | GET | HTML preview of document chunks |
| `/documents/{id}/open` | POST | Open source file |

### Metadata & History

| Endpoint | Method | Description |
|---|---|---|
| `/meta/content_types` | GET | Content type enum |
| `/meta/regions` | GET | Indexed region list |
| `/meta/items` | GET | Indexed entity name list |
| `/history/{session_id}` | GET | Retrieve chat history |
| `/history/{session_id}` | DELETE | Clear chat history |
| `/healthz` | GET | Dependency connectivity status |

## Data Model

### Milvus Collection: `easytour_chunks_v1`

Filter fields (explicit schema): `document_id` / `content_type` / `primary_item_name` / `province` / `city` / `region_path` / `chunk_hash` / `ingest_batch_id` / `created_at`

Display fields (dynamic): `entity_names` / `tips` / `notes` / `opening_hours` / `ticket_price` / `best_season` / `suitable_for` / `attraction_features` / `route_days` / `route_budget` / `price_range` / `hotel_tags` / `food_tags`

### MongoDB Collections

| Collection | Purpose |
|---|---|
| `chat_message` | Conversation history |
| `documents` | Document metadata + chunks snapshot (for metadata_only / reindex rollback) |
| `entity_aliases` | Alias dictionary (alias → canonical name) |
| `retrieval_trace` | Retrieval debug log (topk / scores / expr / latency) |

## Testing

```bash
# Unit tests (no running service required)
python -m pytest tests/ -v --ignore=tests/test_integration_e2e.py

# Integration tests (requires service on localhost:8000)
python -m pytest tests/test_integration_e2e.py -v -s
```

Test coverage:
- `test_utils.py` — region normalizer, hashing, Milvus expr builder, entity hit boosting
- `test_import_nodes.py` — doc-level / chunk-level extraction, entity name recognition
- `test_services.py` — DocumentService, TraceService, API endpoints
- `test_query_graph_behavior.py` — query graph node behavior
- `test_query_graph_parallel.py` — parallel retrieval
- `test_query_nodes_partial_updates.py` — partial node updates
- `test_query_semantic_parity.py` — semantic consistency
- `test_integration_e2e.py` — end-to-end upload / query / dedup / metadata_only / citations

## Environment Variables

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | Primary API key (OpenAI-compatible). `DASHSCOPE_API_KEY` also accepted as fallback. |
| `OPENAI_API_BASE` | API base URL (defaults to DashScope compatible endpoint) |
| `LLM_DEFAULT_MODEL` | LLM model name (default: `qwen-flash`) |
| `EMBEDDING_MODEL` | Embedding model name |
| `EMBEDDING_DIM` | Vector dimension (default: 1024) |
| `MONGO_URL` | MongoDB connection string |
| `MONGO_DB_NAME` | Database name (default: `easytour`) |
| `MILVUS_HOST` / `MILVUS_PORT` | Milvus address |
| `CHUNKS_COLLECTION` | Milvus collection name (default: `easytour_chunks_v1`) |
| `ITEM_NAME_COLLECTION` | Item name collection (default: `easytour_item_names_v1`) |
| `REBUILD_MILVUS_COLLECTION` | `true` to drop and rebuild collection on import (dev only) |
| `ENABLE_WEB_SEARCH` | Enable web search augmentation (default: `true`) |
| `MINERU_API_KEY` / `MINERU_API_BASE` | PDF parsing service config |
| `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` | Object storage config |
