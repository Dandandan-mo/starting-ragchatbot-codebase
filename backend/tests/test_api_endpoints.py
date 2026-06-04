"""
API endpoint tests for the RAG chatbot FastAPI application.

Uses a minimal test app (test_app / test_client from conftest.py) that mirrors
the production endpoints without the static-file mount so tests run without
a frontend directory present.

Test groups:
  TestQueryEndpoint   – POST /api/query  request/response contract
  TestCoursesEndpoint – GET  /api/courses statistics
  TestSessionEndpoint – DELETE /api/session/{id} cleanup
"""
import pytest
from unittest.mock import MagicMock


# ────────────────────────────────────────────────────────────────────────────
# POST /api/query
# ────────────────────────────────────────────────────────────────────────────

class TestQueryEndpoint:

    def test_returns_200_with_answer(self, test_client, mock_rag_system):
        mock_rag_system.query.return_value = ("Python is a language", [])

        resp = test_client.post("/api/query", json={"query": "What is Python?"})

        assert resp.status_code == 200
        assert resp.json()["answer"] == "Python is a language"

    def test_response_includes_session_id(self, test_client, mock_rag_system):
        mock_rag_system.query.return_value = ("OK", [])

        resp = test_client.post("/api/query", json={"query": "hello"})

        assert "session_id" in resp.json()
        assert resp.json()["session_id"]  # non-empty

    def test_creates_session_when_none_provided(self, test_client, mock_rag_system):
        mock_rag_system.query.return_value = ("OK", [])

        resp = test_client.post("/api/query", json={"query": "hello"})

        # The route creates a session; the returned ID must start with "session_"
        assert resp.json()["session_id"].startswith("session_")

    def test_uses_provided_session_id(self, test_client, mock_rag_system):
        mock_rag_system.query.return_value = ("OK", [])
        provided = "session_42"

        resp = test_client.post(
            "/api/query", json={"query": "hello", "session_id": provided}
        )

        assert resp.json()["session_id"] == provided

    def test_passes_query_text_to_rag_system(self, test_client, mock_rag_system):
        mock_rag_system.query.return_value = ("OK", [])

        test_client.post("/api/query", json={"query": "What is FastAPI?"})

        mock_rag_system.query.assert_called_once()
        call_args = mock_rag_system.query.call_args
        assert call_args[0][0] == "What is FastAPI?"

    def test_returns_sources_list(self, test_client, mock_rag_system):
        sources = [
            {"label": "Python 101 – Lesson 1", "url": "https://example.com/1"}
        ]
        mock_rag_system.query.return_value = ("Some answer", sources)

        resp = test_client.post("/api/query", json={"query": "Python?"})

        assert resp.status_code == 200
        returned_sources = resp.json()["sources"]
        assert len(returned_sources) == 1
        assert returned_sources[0]["label"] == "Python 101 – Lesson 1"
        assert returned_sources[0]["url"] == "https://example.com/1"

    def test_empty_sources_when_no_tool_used(self, test_client, mock_rag_system):
        mock_rag_system.query.return_value = ("Direct answer", [])

        resp = test_client.post("/api/query", json={"query": "2 + 2?"})

        assert resp.json()["sources"] == []

    def test_missing_query_field_returns_422(self, test_client):
        resp = test_client.post("/api/query", json={"session_id": "s1"})

        assert resp.status_code == 422

    def test_rag_exception_returns_500(self, test_client, mock_rag_system):
        mock_rag_system.query.side_effect = RuntimeError("Vector DB unreachable")

        resp = test_client.post("/api/query", json={"query": "test"})

        assert resp.status_code == 500
        assert "Vector DB unreachable" in resp.json()["detail"]

    def test_session_id_passed_to_rag_query(self, test_client, mock_rag_system):
        """session_id supplied by client is forwarded to RAGSystem.query()."""
        mock_rag_system.query.return_value = ("OK", [])
        provided = "session_99"

        test_client.post(
            "/api/query", json={"query": "follow-up", "session_id": provided}
        )

        _, kwargs_sid = mock_rag_system.query.call_args[0][1], None
        actual_sid = mock_rag_system.query.call_args[0][1]
        assert actual_sid == provided


# ────────────────────────────────────────────────────────────────────────────
# GET /api/courses
# ────────────────────────────────────────────────────────────────────────────

class TestCoursesEndpoint:

    def test_returns_200_with_course_stats(self, test_client, mock_rag_system):
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 3,
            "course_titles": ["Course A", "Course B", "Course C"],
        }

        resp = test_client.get("/api/courses")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_courses"] == 3
        assert data["course_titles"] == ["Course A", "Course B", "Course C"]

    def test_empty_catalog(self, test_client, mock_rag_system):
        mock_rag_system.get_course_analytics.return_value = {
            "total_courses": 0,
            "course_titles": [],
        }

        resp = test_client.get("/api/courses")

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_courses"] == 0
        assert data["course_titles"] == []

    def test_analytics_exception_returns_500(self, test_client, mock_rag_system):
        mock_rag_system.get_course_analytics.side_effect = RuntimeError("DB error")

        resp = test_client.get("/api/courses")

        assert resp.status_code == 500
        assert "DB error" in resp.json()["detail"]

    def test_response_schema(self, test_client, mock_rag_system):
        """Response always contains exactly total_courses and course_titles."""
        resp = test_client.get("/api/courses")

        assert resp.status_code == 200
        keys = set(resp.json().keys())
        assert keys == {"total_courses", "course_titles"}


# ────────────────────────────────────────────────────────────────────────────
# DELETE /api/session/{session_id}
# ────────────────────────────────────────────────────────────────────────────

class TestSessionEndpoint:

    def test_delete_existing_session_returns_204(self, test_client, mock_rag_system):
        session_id = mock_rag_system.session_manager.create_session()

        resp = test_client.delete(f"/api/session/{session_id}")

        assert resp.status_code == 204

    def test_delete_removes_session_from_manager(self, test_client, mock_rag_system):
        session_id = mock_rag_system.session_manager.create_session()
        mock_rag_system.session_manager.add_exchange(session_id, "q", "a")

        test_client.delete(f"/api/session/{session_id}")

        # Session no longer exists — history returns None
        history = mock_rag_system.session_manager.get_conversation_history(session_id)
        assert history is None

    def test_delete_nonexistent_session_returns_204(self, test_client):
        """Deleting an unknown session is idempotent — no error raised."""
        resp = test_client.delete("/api/session/does-not-exist")

        assert resp.status_code == 204
