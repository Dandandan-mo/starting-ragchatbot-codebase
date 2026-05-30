"""
Tests for AIGenerator – tool-calling flow, message construction, and edge cases.

Tests are grouped into:
  TestGenerateResponseDirect   – queries answered without tool use
  TestToolExecutionLoop        – queries that trigger 1 or 2 sequential tool rounds
  TestEdgeCases                – documents confirmed bugs (empty content lists)
"""
import pytest
from unittest.mock import MagicMock, call

from ai_generator import AIGenerator


# ────────────────────────────────────────────────────────────────────────────
# Direct response (no tool use)
# ────────────────────────────────────────────────────────────────────────────

class TestGenerateResponseDirect:

    def test_direct_response_returns_text(self, ai_generator_instance, make_text_response):
        """Happy-path: direct answer is returned as a plain string."""
        ai_generator_instance.client.messages.create.return_value = make_text_response("Direct answer")

        result = ai_generator_instance.generate_response(query="What is 2+2?")

        assert result == "Direct answer"

    def test_direct_response_makes_exactly_one_api_call(self, ai_generator_instance, make_text_response):
        """No extra API calls when Claude answers directly."""
        ai_generator_instance.client.messages.create.return_value = make_text_response("Answer")

        ai_generator_instance.generate_response(query="test")

        assert ai_generator_instance.client.messages.create.call_count == 1

    def test_direct_no_history_uses_base_system_prompt(self, ai_generator_instance, make_text_response):
        """When conversation_history is None, system equals SYSTEM_PROMPT exactly."""
        ai_generator_instance.client.messages.create.return_value = make_text_response("Answer")

        ai_generator_instance.generate_response(query="test")

        call_kwargs = ai_generator_instance.client.messages.create.call_args[1]
        assert call_kwargs["system"] == AIGenerator.SYSTEM_PROMPT
        assert "Previous conversation" not in call_kwargs["system"]

    def test_conversation_history_included_in_system_prompt(self, ai_generator_instance, make_text_response):
        """History is appended to the system prompt under 'Previous conversation:'."""
        ai_generator_instance.client.messages.create.return_value = make_text_response("Answer")
        history = "User: Hello\nAssistant: Hi there"

        ai_generator_instance.generate_response(query="Follow-up", conversation_history=history)

        call_kwargs = ai_generator_instance.client.messages.create.call_args[1]
        assert "Previous conversation:" in call_kwargs["system"]
        assert "User: Hello" in call_kwargs["system"]
        assert "Assistant: Hi there" in call_kwargs["system"]
        assert call_kwargs["system"].startswith(AIGenerator.SYSTEM_PROMPT)

    def test_tools_absent_from_api_call_when_not_provided(self, ai_generator_instance, make_text_response):
        """When tools=None, neither 'tools' nor 'tool_choice' appear in the call."""
        ai_generator_instance.client.messages.create.return_value = make_text_response("Answer")

        ai_generator_instance.generate_response(query="test")

        call_kwargs = ai_generator_instance.client.messages.create.call_args[1]
        assert "tools" not in call_kwargs
        assert "tool_choice" not in call_kwargs

    def test_tools_included_in_api_call_when_provided(self, ai_generator_instance, make_text_response, mock_tool_manager):
        """When tools are provided, 'tools' and 'tool_choice' are in the call."""
        ai_generator_instance.client.messages.create.return_value = make_text_response("Answer")
        tool_defs = [{"name": "search_course_content"}]

        ai_generator_instance.generate_response(
            query="test", tools=tool_defs, tool_manager=mock_tool_manager
        )

        call_kwargs = ai_generator_instance.client.messages.create.call_args[1]
        assert call_kwargs["tools"] == tool_defs
        assert call_kwargs["tool_choice"] == {"type": "auto"}


# ────────────────────────────────────────────────────────────────────────────
# Tool execution loop (1 or 2 sequential rounds)
# ────────────────────────────────────────────────────────────────────────────

class TestToolExecutionLoop:

    # ── Setup helpers ────────────────────────────────────────────────────────

    def _setup_one_round(self, ai_gen, make_tool_use_response, make_text_response,
                         tool_id="t1", tool_name="search_course_content",
                         tool_input=None, final_text="Final answer"):
        """1 tool round → 2 API calls total."""
        tool_input = tool_input or {"query": "python basics"}
        ai_gen.client.messages.create.side_effect = [
            make_tool_use_response(tool_id, tool_name, tool_input),
            make_text_response(final_text),
        ]

    def _setup_two_rounds(self, ai_gen, make_tool_use_response, make_text_response,
                          final_text="Final answer after two rounds"):
        """2 tool rounds → 3 API calls total."""
        ai_gen.client.messages.create.side_effect = [
            make_tool_use_response("t1", "search_course_content", {"query": "course X outline"}),
            make_tool_use_response("t2", "search_course_content", {"query": "lesson 4 topic"}),
            make_text_response(final_text),
        ]

    # ── Single round ─────────────────────────────────────────────────────────

    def test_tool_use_triggers_execution(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """When stop_reason='tool_use', tool_manager.execute_tool is called."""
        self._setup_one_round(ai_generator_instance, make_tool_use_response, make_text_response)

        ai_generator_instance.generate_response(
            query="What is Python?",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        mock_tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="python basics"
        )

    def test_single_round_makes_two_api_calls(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """One tool round results in exactly 2 calls to messages.create."""
        self._setup_one_round(ai_generator_instance, make_tool_use_response, make_text_response)

        ai_generator_instance.generate_response(
            query="test", tools=[{"name": "search_course_content"}], tool_manager=mock_tool_manager
        )

        assert ai_generator_instance.client.messages.create.call_count == 2

    def test_final_response_text_returned(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """The text from the post-tool API call is what's returned."""
        self._setup_one_round(
            ai_generator_instance, make_tool_use_response, make_text_response,
            final_text="Python is a programming language"
        )

        result = ai_generator_instance.generate_response(
            query="What is Python?",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        assert result == "Python is a programming language"

    def test_tool_execution_message_format(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """
        Synthesis call (2nd API call) must send exactly 3 messages in the correct structure:
          [0] user – original query
          [1] assistant – the tool_use content blocks
          [2] user – list of tool_result blocks
        """
        mock_tool_manager.execute_tool.return_value = "Found: python content"
        self._setup_one_round(
            ai_generator_instance, make_tool_use_response, make_text_response,
            tool_id="t1", tool_input={"query": "python basics"}
        )

        ai_generator_instance.generate_response(
            query="What is Python?",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        second_call_kwargs = ai_generator_instance.client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]

        assert len(messages) == 3

        # Message 0: original user query
        assert messages[0] == {"role": "user", "content": "What is Python?"}

        # Message 1: assistant echoing back its tool_use decision
        assert messages[1]["role"] == "assistant"
        assert isinstance(messages[1]["content"], list)

        # Message 2: tool results
        assert messages[2]["role"] == "user"
        tool_results = messages[2]["content"]
        assert isinstance(tool_results, list)
        assert len(tool_results) == 1
        assert tool_results[0]["type"] == "tool_result"
        assert tool_results[0]["tool_use_id"] == "t1"
        assert tool_results[0]["content"] == "Found: python content"

    def test_synthesis_call_has_no_tools(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """
        The explicit post-loop synthesis call (after MAX_TOOL_ROUNDS are exhausted)
        must NOT include 'tools' or 'tool_choice'.  This prevents Claude from
        looping further once the round cap has been reached.

        Uses the two-round setup (3 API calls) where the synthesis is the 3rd call.
        """
        self._setup_two_rounds(ai_generator_instance, make_tool_use_response, make_text_response)

        ai_generator_instance.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        # 3rd call (index 2) is the post-loop synthesis
        synthesis_call_kwargs = ai_generator_instance.client.messages.create.call_args_list[2][1]
        assert "tools" not in synthesis_call_kwargs
        assert "tool_choice" not in synthesis_call_kwargs

    def test_all_calls_preserve_system_prompt(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """The system prompt is forwarded unchanged to every API call in a two-round sequence."""
        self._setup_two_rounds(ai_generator_instance, make_tool_use_response, make_text_response)
        history = "User: prior\nAssistant: reply"

        ai_generator_instance.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
            conversation_history=history,
        )

        systems = [
            ai_generator_instance.client.messages.create.call_args_list[i][1]["system"]
            for i in range(3)
        ]
        assert systems[0] == systems[1] == systems[2]

    # ── Two rounds ───────────────────────────────────────────────────────────

    def test_two_rounds_makes_three_api_calls(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """Two tool rounds result in exactly 3 calls: round1, round2, synthesis."""
        self._setup_two_rounds(ai_generator_instance, make_tool_use_response, make_text_response)

        ai_generator_instance.generate_response(
            query="Find a course on the same topic as lesson 4 of course X",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        assert ai_generator_instance.client.messages.create.call_count == 3

    def test_two_rounds_executes_tool_twice(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """execute_tool is called once per round — twice in a two-round sequence."""
        self._setup_two_rounds(ai_generator_instance, make_tool_use_response, make_text_response)

        ai_generator_instance.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        assert mock_tool_manager.execute_tool.call_count == 2

    def test_two_rounds_returns_final_text(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """The text from the third (synthesis) API call is what's returned."""
        self._setup_two_rounds(
            ai_generator_instance, make_tool_use_response, make_text_response,
            final_text="Here is your multi-search answer"
        )

        result = ai_generator_instance.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        assert result == "Here is your multi-search answer"

    def test_two_rounds_message_list_has_five_entries(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """
        After two tool rounds the synthesis call receives 5 messages:
          [0] user  – original query
          [1] assistant – round-1 tool_use blocks
          [2] user  – round-1 tool_results
          [3] assistant – round-2 tool_use blocks
          [4] user  – round-2 tool_results
        """
        self._setup_two_rounds(ai_generator_instance, make_tool_use_response, make_text_response)

        ai_generator_instance.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        synthesis_kwargs = ai_generator_instance.client.messages.create.call_args_list[2][1]
        messages = synthesis_kwargs["messages"]

        assert len(messages) == 5
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert messages[3]["role"] == "assistant"
        assert messages[4]["role"] == "user"

    def test_max_rounds_respected(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """
        Even if Claude keeps requesting tools, the loop hard-stops at MAX_TOOL_ROUNDS.
        Three tool_use responses are mocked but only 2 rounds should run (3 calls total).
        """
        ai_generator_instance.client.messages.create.side_effect = [
            make_tool_use_response("t1", "search_course_content", {"query": "q1"}),
            make_tool_use_response("t2", "search_course_content", {"query": "q2"}),
            make_tool_use_response("t3", "search_course_content", {"query": "q3"}),
            make_text_response("Final"),
        ]

        ai_generator_instance.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        # 2 tool rounds + 1 synthesis = 3 total (not 4)
        assert ai_generator_instance.client.messages.create.call_count == 3

    # ── Error handling ───────────────────────────────────────────────────────

    def test_tool_execution_error_breaks_loop(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """
        When execute_tool raises, the loop stops after one round (2 total API calls).
        No exception propagates to the caller — Claude receives the error as context.
        """
        mock_tool_manager.execute_tool.side_effect = RuntimeError("DB unavailable")
        ai_generator_instance.client.messages.create.side_effect = [
            make_tool_use_response("t1", "search_course_content", {"query": "q1"}),
            make_text_response("Sorry, search failed"),
        ]

        result = ai_generator_instance.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        assert ai_generator_instance.client.messages.create.call_count == 2
        assert isinstance(result, str)

    def test_tool_execution_error_result_sent_to_claude(
        self, ai_generator_instance, make_tool_use_response, make_text_response, mock_tool_manager
    ):
        """
        When execute_tool raises, the error text is included in the tool_result
        message sent to Claude so it can provide a graceful degraded answer.
        """
        mock_tool_manager.execute_tool.side_effect = RuntimeError("DB unavailable")
        ai_generator_instance.client.messages.create.side_effect = [
            make_tool_use_response("t1", "search_course_content", {"query": "q1"}),
            make_text_response("Sorry, search failed"),
        ]

        ai_generator_instance.generate_response(
            query="test",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )

        synthesis_kwargs = ai_generator_instance.client.messages.create.call_args_list[1][1]
        tool_result_message = synthesis_kwargs["messages"][2]
        assert tool_result_message["role"] == "user"
        tool_results = tool_result_message["content"]
        assert any("Tool execution failed" in r["content"] for r in tool_results)


# ────────────────────────────────────────────────────────────────────────────
# Edge-case / bug-documenting tests
# ────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:

    def test_empty_content_in_direct_response_raises_value_error(self, ai_generator_instance):
        """
        FIX VERIFIED: When Claude returns content=[], the guard in generate_response()
        raises a descriptive ValueError instead of a bare IndexError.
        This gives a meaningful message in the HTTP 500 detail field.
        """
        empty_response = MagicMock()
        empty_response.stop_reason = "end_turn"
        empty_response.content = []  # triggers the guard
        ai_generator_instance.client.messages.create.return_value = empty_response

        with pytest.raises(ValueError, match="empty response with no content blocks"):
            ai_generator_instance.generate_response(query="What is Python?")

    def test_empty_content_after_tool_use_raises_value_error(
        self, ai_generator_instance, make_tool_use_response, mock_tool_manager
    ):
        """
        FIX VERIFIED: The guard in generate_response() raises ValueError when the
        synthesis call (post-tool) returns empty content.
        This is the more common production trigger because content questions always
        route through tool use.
        """
        tool_response = make_tool_use_response(
            tool_id="t1", tool_name="search_course_content",
            tool_input={"query": "python"}
        )
        empty_final = MagicMock()
        empty_final.stop_reason = "end_turn"
        empty_final.content = []  # triggers the guard on the synthesis call
        ai_generator_instance.client.messages.create.side_effect = [tool_response, empty_final]

        with pytest.raises(ValueError, match="empty final response after tool execution"):
            ai_generator_instance.generate_response(
                query="What is Python?",
                tools=[{"name": "search_course_content"}],
                tool_manager=mock_tool_manager,
            )
