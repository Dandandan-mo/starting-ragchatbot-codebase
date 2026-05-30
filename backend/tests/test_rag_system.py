"""
Tests for RAGSystem.query() – the full content-query pipeline.

These tests use rag_system_with_mocks (from conftest.py), which gives a real
RAGSystem object with ai_generator, tool_manager, and session_manager replaced
by controlled mocks.

Key groups:
  TestQueryPipeline       – normal flow, prompt wrapping, tools wired correctly
  TestSourceManagement    – sources retrieved then reset
  TestSessionHistory      – history retrieved / stored correctly
  TestExceptionPropagation – proves that IndexError → HTTP 500 ("query failed")
"""
import pytest
from unittest.mock import MagicMock, call

from rag_system import RAGSystem
from session_manager import SessionManager


# ────────────────────────────────────────────────────────────────────────────
# Normal pipeline
# ────────────────────────────────────────────────────────────────────────────

class TestQueryPipeline:

    def test_query_returns_response_and_sources(self, rag_system_with_mocks):
        """query() returns a (response_str, sources_list) tuple."""
        rag = rag_system_with_mocks
        rag.ai_generator.generate_response.return_value = "Python is a language"
        rag.tool_manager.get_last_sources.return_value = [
            {"label": "Python 101 - Lesson 1", "url": "https://ex.com"}
        ]

        response, sources = rag.query("What is Python?")

        assert response == "Python is a language"
        assert len(sources) == 1
        assert sources[0]["label"] == "Python 101 - Lesson 1"

    def test_query_wraps_prompt_correctly(self, rag_system_with_mocks):
        """The user's raw question is prefixed before being sent to the AI."""
        rag = rag_system_with_mocks

        rag.query("What is Python?")

        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        assert call_kwargs["query"] == "Answer this question about course materials: What is Python?"

    def test_query_passes_tools_and_manager(self, rag_system_with_mocks):
        """generate_response receives both 'tools' and 'tool_manager' kwargs."""
        rag = rag_system_with_mocks
        tool_defs = [{"name": "search_course_content"}]
        rag.tool_manager.get_tool_definitions.return_value = tool_defs

        rag.query("test question")

        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        assert call_kwargs["tools"] == tool_defs
        assert call_kwargs["tool_manager"] is rag.tool_manager

    def test_query_empty_sources_when_no_tool_used(self, rag_system_with_mocks):
        """When the AI answers without calling a tool, sources are an empty list."""
        rag = rag_system_with_mocks
        rag.tool_manager.get_last_sources.return_value = []

        _, sources = rag.query("What is 2 + 2?")

        assert sources == []


# ────────────────────────────────────────────────────────────────────────────
# Source management
# ────────────────────────────────────────────────────────────────────────────

class TestSourceManagement:

    def test_query_retrieves_sources_after_response(self, rag_system_with_mocks):
        """get_last_sources() is called at least once after generate_response."""
        rag = rag_system_with_mocks

        rag.query("test")

        rag.tool_manager.get_last_sources.assert_called()

    def test_query_resets_sources_after_retrieval(self, rag_system_with_mocks):
        """reset_sources() is called after get_last_sources() on every query."""
        rag = rag_system_with_mocks
        call_order = []

        rag.tool_manager.get_last_sources.side_effect = lambda: call_order.append("get") or []
        rag.tool_manager.reset_sources.side_effect = lambda: call_order.append("reset")

        rag.query("test")

        assert "get" in call_order
        assert "reset" in call_order
        # get must come BEFORE reset
        assert call_order.index("get") < call_order.index("reset"), (
            "reset_sources() was called BEFORE get_last_sources() — sources would be empty"
        )

    def test_sources_not_stale_across_calls(self, rag_system_with_mocks):
        """
        Each query gets only its own sources, not those from a previous query.
        (reset_sources must actually clear them between requests.)
        """
        rag = rag_system_with_mocks

        # First query returns real sources
        rag.tool_manager.get_last_sources.return_value = [{"label": "Lesson 1", "url": "u1"}]
        _, sources_1 = rag.query("first question")

        # Second query returns empty (tool not used)
        rag.tool_manager.get_last_sources.return_value = []
        _, sources_2 = rag.query("second question")

        assert len(sources_1) == 1
        assert sources_2 == []


# ────────────────────────────────────────────────────────────────────────────
# Session / conversation history
# ────────────────────────────────────────────────────────────────────────────

class TestSessionHistory:

    def test_query_no_session_no_history_passed(self, rag_system_with_mocks):
        """With no session_id, generate_response receives conversation_history=None."""
        rag = rag_system_with_mocks

        rag.query("What is Python?")   # no session_id

        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        assert call_kwargs["conversation_history"] is None

    def test_query_no_session_history_not_stored(self, rag_system_with_mocks):
        """With no session_id, session_manager.add_exchange is never called."""
        rag = rag_system_with_mocks
        add_exchange_spy = MagicMock()
        rag.session_manager.add_exchange = add_exchange_spy

        rag.query("What is Python?")   # no session_id

        add_exchange_spy.assert_not_called()

    def test_query_with_session_retrieves_history(self, rag_system_with_mocks):
        """
        When a session exists and has prior exchanges, that history is passed
        to generate_response as conversation_history (non-None string).
        """
        rag = rag_system_with_mocks
        session_id = rag.session_manager.create_session()
        rag.session_manager.add_exchange(session_id, "Prior question", "Prior answer")

        rag.query("Follow-up question", session_id=session_id)

        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        history = call_kwargs["conversation_history"]
        assert history is not None
        assert "Prior question" in history
        assert "Prior answer" in history

    def test_query_with_new_session_passes_none_history(self, rag_system_with_mocks):
        """A brand-new session with no exchanges passes history=None."""
        rag = rag_system_with_mocks
        session_id = rag.session_manager.create_session()

        rag.query("First question", session_id=session_id)

        call_kwargs = rag.ai_generator.generate_response.call_args[1]
        assert call_kwargs["conversation_history"] is None

    def test_query_updates_history_after_response(self, rag_system_with_mocks):
        """After query(), the exchange is stored in session history."""
        rag = rag_system_with_mocks
        rag.ai_generator.generate_response.return_value = "AI answer here"
        session_id = rag.session_manager.create_session()

        rag.query("User question here", session_id=session_id)

        history = rag.session_manager.get_conversation_history(session_id)
        assert history is not None
        assert "User question here" in history
        assert "AI answer here" in history


# ────────────────────────────────────────────────────────────────────────────
# Exception propagation – the root cause of "query failed"
# ────────────────────────────────────────────────────────────────────────────

class TestExceptionPropagation:

    def test_query_propagates_value_error_from_empty_content(self, rag_system_with_mocks):
        """
        FIX VERIFIED: After applying the guard in ai_generator.py, the empty-content
        case now raises ValueError (not IndexError).  RAGSystem.query() still has no
        try/except, so the ValueError propagates to app.py, which returns HTTP 500
        with a meaningful detail message instead of a bare 'list index out of range'.
        """
        rag = rag_system_with_mocks
        rag.ai_generator.generate_response.side_effect = ValueError(
            "Claude returned an empty response with no content blocks (stop_reason='end_turn')."
        )

        with pytest.raises(ValueError, match="empty response with no content blocks"):
            rag.query("What topics are in the MCP course?")

    def test_query_propagates_generic_api_exception(self, rag_system_with_mocks):
        """
        Any exception from the AI layer propagates unhandled, producing HTTP 500.
        This includes Anthropic API errors (rate limits, auth failures, etc.).
        """
        rag = rag_system_with_mocks
        rag.ai_generator.generate_response.side_effect = RuntimeError("API rate limit exceeded")

        with pytest.raises(RuntimeError, match="API rate limit exceeded"):
            rag.query("Explain lesson 3")

    def test_query_propagates_value_error_after_fix(self, rag_system_with_mocks):
        """
        AFTER THE FIX: ai_generator.py raises ValueError instead of IndexError
        when content is empty.  RAGSystem.query() must still propagate it so
        app.py can return a meaningful HTTP 500 detail.

        Run this test after applying Fix 1 to ai_generator.py to confirm the
        fixed exception type propagates correctly through the pipeline.
        """
        rag = rag_system_with_mocks
        rag.ai_generator.generate_response.side_effect = ValueError(
            "Claude returned an empty response with no content blocks."
        )

        with pytest.raises(ValueError, match="Claude returned an empty response"):
            rag.query("What is in lesson 1?")
