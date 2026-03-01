# Hari — Long-Term Memory for LLMs

This project is about **building and comparing different long-term memory options** for LLM applications. It provides storage, retrieval, and RAG-style answering over persisted memories.

## What’s in scope

- **Memory backends**: pluggable storage and retrieval (e.g. SQLite + embeddings, others to come).
- **Embeddings**: semantic search over memory documents.
- **RAG**: retrieve relevant memories and feed them as context to an LLM for grounded answers.

## Current memory options

| Option | Storage | Retrieval | Notes |
|--------|--------|-----------|--------|
| **SQLite + embeddings** | `memory_docs` in SQLite | Cosine similarity over sentence-transformers vectors | Default; uses `sentence-transformers/all-MiniLM-L6-v2`. |

More backends (e.g. dedicated vector DBs, different embedding providers) can be added for comparison.

## Requirements

- Python 3.8+
- See `requirements.txt` for dependencies (e.g. `fastapi`, `uvicorn`, `sentence-transformers`, `numpy` for full memory/RAG).

Optional: [Ollama](https://ollama.ai/) (or another LLM via `llm_providers`) for RAG generation.

## Setup

```bash
pip install -r requirements.txt
```

Copy `config.json.example` to `config.json` and adjust (e.g. LLM provider). Data is stored under `~/.hari/` (SQLite DB and optional config).

## Run

```bash
python hari.py run
```

This starts the service (API and in-process components). Default API: `http://127.0.0.1:8765` (set `HARI_API_PORT` to override).

## Project layout

```
hari/
├── hari.py           # Entry point (run)
├── hari_services.py  # Services: memory layer, LLM, Web API
├── llm_providers.py # LLM provider abstraction (Ollama, Bedrock, …)
├── schema.sql       # DB schema (analytics/memory tables)
├── config.json.example
├── requirements.txt
└── frontend/        # Optional Next.js UI (uses the API)
```

## License

To be determined.
