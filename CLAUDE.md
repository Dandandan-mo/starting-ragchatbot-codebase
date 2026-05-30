# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup & Running

Always use `uv` to run the server, run Python files, and manage all dependencies — never `pip` or `python` directly.

```bash
# Install dependencies
uv sync

# Create .env in project root
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# Run the app (from project root)
./run.sh
# or manually:
cd backend && uv run uvicorn app:app --reload --port 8000
```

App runs at `http://localhost:8000`. API docs at `http://localhost:8000/docs`.

Unless specified in prompt, don't auto run the server for me at the end of the code change, I'd like to manually run it myself.

## Architecture

Full-stack RAG chatbot: FastAPI backend + static HTML/JS/CSS frontend. The backend serves the frontend as static files.

**Request flow:**
1. `frontend/script.js` POSTs `{ query, session_id }` to `/api/query`
2. `app.py` routes to `RAGSystem.query()`
3. `RAGSystem` passes the query to `AIGenerator` with a `search_course_content` tool available
4. Claude decides whether to call the tool. If it does, `VectorStore.search()` runs a semantic search against ChromaDB and returns the top-5 chunks
5. Tool results are appended to the message history and Claude makes a second API call to produce the final answer
6. Sources and answer are returned to the frontend

**Key component responsibilities:**
- `backend/rag_system.py` — orchestrator; owns the query pipeline and wires all components together
- `backend/ai_generator.py` — Claude API calls; handles the tool-use loop (first call with tools, second call after tool results)
- `backend/vector_store.py` — ChromaDB wrapper with two collections: `course_catalog` (course-level metadata for fuzzy name resolution) and `course_content` (text chunks for retrieval)
- `backend/document_processor.py` — parses `.txt` course files into `Course`/`Lesson`/`CourseChunk` models and splits text into overlapping sentence-based chunks
- `backend/search_tools.py` — defines the `search_course_content` tool Claude calls, plus `ToolManager` for registration and dispatch
- `backend/session_manager.py` — in-memory conversation history (not persisted across restarts), capped at `MAX_HISTORY=2` exchanges
- `backend/config.py` — single source of truth for model name, chunk sizes, ChromaDB path, etc.

## Course Document Format

Files in `docs/` must follow this structure for `DocumentProcessor` to parse them correctly:

```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 0: <title>
Lesson Link: <url>
<lesson text...>

Lesson 1: <title>
...
```

Course title is used as the unique ID in ChromaDB — duplicate titles are skipped on startup.

## Key Design Decisions

- **Tool-based retrieval**: Claude autonomously decides when to search rather than always pre-fetching context. One search per query maximum (enforced by the system prompt).
- **Two-collection ChromaDB setup**: `course_catalog` enables fuzzy course-name resolution (e.g. "MCP course" → exact title) before filtering `course_content` chunks.
- **Session IDs are client-managed**: The frontend stores `currentSessionId` in memory and sends it with each request. A `null` session_id triggers server-side creation.
- **Chunking is sentence-based**: `chunk_text()` splits on sentence boundaries (not fixed character positions) to avoid cutting mid-sentence, then applies character-level overlap between chunks.
