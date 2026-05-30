"""
Shared test configuration, sys.path setup, and fixtures for the RAG chatbot test suite.

This conftest.py must run BEFORE any backend module is imported.
The top-level sys.path and sys.modules stubs accomplish that guarantee.
"""
import sys
import os
from unittest.mock import MagicMock, patch

# ── 1. Make backend/ importable with flat relative imports ──────────────────
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# ── 2. Stub heavy / disk-touching third-party modules BEFORE backend imports ─
#    chromadb and sentence_transformers would try to load GPU models and open
#    disk files when their modules are imported.  Replace them with mocks so
#    every test runs in < 1 second without any infrastructure.
for mod in [
    "chromadb",
    "chromadb.config",
    "chromadb.utils",
    "chromadb.utils.embedding_functions",
    "sentence_transformers",
]:
    sys.modules.setdefault(mod, MagicMock())

# ── 3. Also stub dotenv so Config() doesn't error if .env is absent ─────────
sys.modules.setdefault("dotenv", MagicMock())

import pytest

# Now it is safe to import from the backend
from vector_store import SearchResults, VectorStore
from search_tools import CourseSearchTool, ToolManager
from ai_generator import AIGenerator


# ────────────────────────────────────────────────────────────────────────────
# Sample data fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_search_results():
    """Two-document SearchResults with realistic metadata."""
    return SearchResults(
        documents=[
            "Python fundamentals content here.",
            "Advanced Python concepts explained.",
        ],
        metadata=[
            {
                "course_title": "Python for Beginners",
                "lesson_number": 1,
                "lesson_link": "https://ex.com/1",
            },
            {
                "course_title": "Python for Beginners",
                "lesson_number": 2,
                "lesson_link": "https://ex.com/2",
            },
        ],
        distances=[0.1, 0.3],
    )


@pytest.fixture
def empty_search_results():
    """SearchResults with no documents (no error)."""
    return SearchResults(documents=[], metadata=[], distances=[])


@pytest.fixture
def error_search_results():
    """SearchResults carrying an error message."""
    return SearchResults.empty("Search error: connection timeout")


# ────────────────────────────────────────────────────────────────────────────
# VectorStore mock
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_vector_store(sample_search_results):
    """MagicMock VectorStore that returns sample results by default."""
    store = MagicMock(spec=VectorStore)
    store.search.return_value = sample_search_results
    return store


# ────────────────────────────────────────────────────────────────────────────
# Anthropic response factories
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def make_text_response():
    """
    Factory fixture.  Usage:
        resp = make_text_response("Hello world")
    Returns a mock Message with stop_reason='end_turn' and one TextBlock.
    """
    def _factory(text: str):
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = text

        response = MagicMock()
        response.stop_reason = "end_turn"
        response.content = [text_block]
        return response

    return _factory


@pytest.fixture
def make_tool_use_response():
    """
    Factory fixture.  Usage:
        resp = make_tool_use_response(
            tool_id="t1",
            tool_name="search_course_content",
            tool_input={"query": "python"},
        )
    Returns a mock Message with stop_reason='tool_use' and one ToolUseBlock.
    """
    def _factory(tool_id: str, tool_name: str, tool_input: dict):
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.id = tool_id
        tool_block.name = tool_name
        tool_block.input = tool_input

        response = MagicMock()
        response.stop_reason = "tool_use"
        response.content = [tool_block]
        return response

    return _factory


# ────────────────────────────────────────────────────────────────────────────
# AIGenerator fixture (mocked Anthropic client)
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_anthropic_client():
    """A MagicMock standing in for the anthropic.Anthropic client."""
    return MagicMock()


@pytest.fixture
def ai_generator_instance(mock_anthropic_client):
    """
    AIGenerator with a mocked Anthropic client injected.
    Bypasses __init__ to avoid real API-key validation.
    """
    gen = AIGenerator.__new__(AIGenerator)
    gen.client = mock_anthropic_client
    gen.model = "claude-test-model"
    gen.base_params = {
        "model": "claude-test-model",
        "temperature": 0,
        "max_tokens": 800,
    }
    return gen


# ────────────────────────────────────────────────────────────────────────────
# ToolManager mock
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_tool_manager():
    """MagicMock ToolManager whose execute_tool returns a canned string."""
    mgr = MagicMock(spec=ToolManager)
    mgr.execute_tool.return_value = "Tool result: found relevant content"
    mgr.get_tool_definitions.return_value = [
        {"name": "search_course_content", "description": "Search courses"}
    ]
    mgr.get_last_sources.return_value = []
    return mgr


# ────────────────────────────────────────────────────────────────────────────
# RAGSystem fixture (all external deps mocked)
# ────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def rag_system_with_mocks(mock_anthropic_client, mock_tool_manager):
    """
    Returns a RAGSystem with every external dependency replaced by mocks.
    Patches chromadb at construction time so VectorStore doesn't hit disk.
    """
    from unittest.mock import patch, MagicMock
    from rag_system import RAGSystem

    # Build a minimal config-like object
    cfg = MagicMock()
    cfg.CHUNK_SIZE = 800
    cfg.CHUNK_OVERLAP = 100
    cfg.CHROMA_PATH = "./chroma_db"
    cfg.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    cfg.MAX_RESULTS = 5
    cfg.MAX_HISTORY = 2
    cfg.ANTHROPIC_API_KEY = "test-key"
    cfg.ANTHROPIC_MODEL = "claude-test-model"

    with patch("rag_system.VectorStore"), patch("rag_system.AIGenerator"), patch("rag_system.chromadb", MagicMock(), create=True):
        rag = RAGSystem(cfg)

    # Replace auto-created components with controlled mocks
    rag.ai_generator = MagicMock()
    rag.ai_generator.generate_response.return_value = "Mocked AI response"

    rag.tool_manager = mock_tool_manager
    mock_tool_manager.get_last_sources.return_value = []

    # Keep session_manager real for accurate history tests
    from session_manager import SessionManager
    rag.session_manager = SessionManager(max_history=2)

    return rag
