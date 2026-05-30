"""
Tests for CourseSearchTool.execute() and ToolManager source management.

The tests cover:
- Happy-path result formatting
- Empty result messages (with/without filters)
- Error propagation
- Source tracking in last_sources
- Graceful handling of missing metadata fields
- ToolManager source reset
"""
import pytest
from unittest.mock import MagicMock

from vector_store import SearchResults, VectorStore
from search_tools import CourseSearchTool, ToolManager


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _make_tool(mock_vector_store) -> CourseSearchTool:
    return CourseSearchTool(mock_vector_store)


# ────────────────────────────────────────────────────────────────────────────
# CourseSearchTool.execute() – happy path
# ────────────────────────────────────────────────────────────────────────────

class TestCourseSearchToolExecute:

    def test_execute_with_results_found(self, mock_vector_store, sample_search_results):
        """Result contains formatted headers and document content."""
        tool = _make_tool(mock_vector_store)
        result = tool.execute(query="what is python")

        assert "[Python for Beginners - Lesson 1]" in result
        assert "[Python for Beginners - Lesson 2]" in result
        assert "Python fundamentals content here." in result
        assert "Advanced Python concepts explained." in result

    def test_execute_calls_store_with_correct_args(self, mock_vector_store):
        """All three search arguments are forwarded to store.search()."""
        tool = _make_tool(mock_vector_store)
        tool.execute(query="loops", course_name="Python 101", lesson_number=3)

        mock_vector_store.search.assert_called_once_with(
            query="loops",
            course_name="Python 101",
            lesson_number=3,
        )

    def test_execute_calls_store_with_none_defaults(self, mock_vector_store):
        """Optional args default to None when not supplied."""
        tool = _make_tool(mock_vector_store)
        tool.execute(query="what is python")

        mock_vector_store.search.assert_called_once_with(
            query="what is python",
            course_name=None,
            lesson_number=None,
        )

    # ── Empty results ────────────────────────────────────────────────────────

    def test_execute_empty_results_no_filters(self, mock_vector_store, empty_search_results):
        """No-filter empty result returns the base message."""
        mock_vector_store.search.return_value = empty_search_results
        tool = _make_tool(mock_vector_store)

        result = tool.execute(query="obscure topic")

        assert result == "No relevant content found."

    def test_execute_empty_results_with_course_name(self, mock_vector_store, empty_search_results):
        """Course-name filter is appended to the empty-results message."""
        mock_vector_store.search.return_value = empty_search_results
        tool = _make_tool(mock_vector_store)

        result = tool.execute(query="obscure topic", course_name="Python 101")

        assert result == "No relevant content found in course 'Python 101'."

    def test_execute_empty_results_with_lesson_number(self, mock_vector_store, empty_search_results):
        """Lesson-number filter is appended to the empty-results message."""
        mock_vector_store.search.return_value = empty_search_results
        tool = _make_tool(mock_vector_store)

        result = tool.execute(query="obscure topic", lesson_number=5)

        assert result == "No relevant content found in lesson 5."

    def test_execute_empty_results_with_both_filters(self, mock_vector_store, empty_search_results):
        """Both filters appear in the empty-results message."""
        mock_vector_store.search.return_value = empty_search_results
        tool = _make_tool(mock_vector_store)

        result = tool.execute(query="obscure topic", course_name="Python 101", lesson_number=3)

        assert "in course 'Python 101'" in result
        assert "in lesson 3" in result

    # ── Error results ────────────────────────────────────────────────────────

    def test_execute_error_returns_error_string(self, mock_vector_store, error_search_results):
        """When SearchResults carries an error, that string is returned verbatim."""
        mock_vector_store.search.return_value = error_search_results
        tool = _make_tool(mock_vector_store)

        result = tool.execute(query="anything")

        assert result == "Search error: connection timeout"

    # ── Source tracking ──────────────────────────────────────────────────────

    def test_execute_tracks_last_sources(self, mock_vector_store, sample_search_results):
        """last_sources is populated with label+url dicts after a successful search."""
        tool = _make_tool(mock_vector_store)
        tool.execute(query="what is python")

        assert len(tool.last_sources) == 2
        assert tool.last_sources[0] == {
            "label": "Python for Beginners - Lesson 1",
            "url": "https://ex.com/1",
        }
        assert tool.last_sources[1] == {
            "label": "Python for Beginners - Lesson 2",
            "url": "https://ex.com/2",
        }

    def test_execute_no_sources_on_empty_results(self, mock_vector_store, empty_search_results):
        """last_sources must NOT be modified when the search returns empty."""
        mock_vector_store.search.return_value = empty_search_results
        tool = _make_tool(mock_vector_store)
        # Pre-populate to verify it stays unchanged
        tool.last_sources = []

        tool.execute(query="nothing")

        assert tool.last_sources == []

    def test_execute_no_sources_on_error(self, mock_vector_store, error_search_results):
        """last_sources must NOT be modified when the search returns an error."""
        mock_vector_store.search.return_value = error_search_results
        tool = _make_tool(mock_vector_store)
        tool.last_sources = []

        tool.execute(query="nothing")

        assert tool.last_sources == []

    # ── Metadata resilience ──────────────────────────────────────────────────

    def test_format_missing_course_title_defaults_to_unknown(self, mock_vector_store):
        """Missing 'course_title' key falls back to 'unknown' in the header."""
        mock_vector_store.search.return_value = SearchResults(
            documents=["Some content."],
            metadata=[{}],          # completely empty metadata
            distances=[0.5],
        )
        tool = _make_tool(mock_vector_store)
        result = tool.execute(query="test")

        assert "[unknown]" in result
        assert "Some content." in result
        # Sources label should also default to "unknown" with no lesson suffix
        assert tool.last_sources[0]["label"] == "unknown"
        assert tool.last_sources[0]["url"] == ""

    def test_format_missing_lesson_number_omits_lesson_from_header(self, mock_vector_store):
        """Missing 'lesson_number' omits the '- Lesson N' suffix from header and label."""
        mock_vector_store.search.return_value = SearchResults(
            documents=["Course intro content."],
            metadata=[{"course_title": "Python 101", "lesson_link": "https://ex.com"}],
            distances=[0.2],
        )
        tool = _make_tool(mock_vector_store)
        result = tool.execute(query="test")

        assert "[Python 101]" in result
        assert "Lesson" not in result.split("[Python 101]")[0] + "[Python 101]"
        assert tool.last_sources[0]["label"] == "Python 101"


# ────────────────────────────────────────────────────────────────────────────
# ToolManager source management
# ────────────────────────────────────────────────────────────────────────────

class TestToolManager:

    def test_tool_manager_get_last_sources_from_registered_tool(self, mock_vector_store, sample_search_results):
        """get_last_sources() delegates to the registered tool's last_sources."""
        mgr = ToolManager()
        tool = CourseSearchTool(mock_vector_store)
        mgr.register_tool(tool)

        # Simulate a search that populates last_sources
        tool.execute(query="python")

        sources = mgr.get_last_sources()
        assert len(sources) == 2
        assert sources[0]["label"] == "Python for Beginners - Lesson 1"

    def test_tool_manager_reset_clears_sources(self, mock_vector_store, sample_search_results):
        """reset_sources() sets last_sources back to [] on all registered tools."""
        mgr = ToolManager()
        tool = CourseSearchTool(mock_vector_store)
        mgr.register_tool(tool)

        tool.execute(query="python")
        assert len(mgr.get_last_sources()) == 2  # sanity check

        mgr.reset_sources()

        assert mgr.get_last_sources() == []
        assert tool.last_sources == []
