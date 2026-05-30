import anthropic
from typing import List, Optional

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Search Tool Usage:
- Use `search_course_content` for questions about specific course content or detailed educational materials
- Use `get_course_outline` for questions about course structure, syllabus, lesson list, or what topics a course covers — it returns the course title, course link, and a numbered list of all lessons
- **Up to 2 sequential tool calls per query** — use a second call only when the first result is insufficient to answer the question fully
- Synthesize results into accurate, fact-based responses
- If a tool yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Search first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    MAX_TOOL_ROUNDS = 2

    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Supports up to MAX_TOOL_ROUNDS sequential tool calls. Each round is a
        separate API request so Claude can reason about previous results before
        deciding whether to search again.

        Terminates when:
          (a) MAX_TOOL_ROUNDS rounds completed
          (b) Claude's response contains no tool_use blocks
          (c) A tool execution raises an exception (error surfaced to Claude)

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        # Build system content — avoid string ops when no history present
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        # Prepare initial API call parameters
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content
        }

        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}

        tool_rounds_run = 0
        response = None

        for _ in range(self.MAX_TOOL_ROUNDS):
            response = self.client.messages.create(**api_params)

            # Condition (b): no tool use — Claude answered directly this iteration
            if response.stop_reason != "tool_use" or not tool_manager:
                break

            # Execute all tool calls in this round
            tool_results = []
            error_occurred = False
            for block in response.content:
                if block.type == "tool_use":
                    try:
                        result = tool_manager.execute_tool(block.name, **block.input)
                    except Exception as e:
                        result = f"Tool execution failed: {e}"
                        error_occurred = True
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            # Grow the message list with this round's exchange
            api_params["messages"].append({"role": "assistant", "content": response.content})
            api_params["messages"].append({"role": "user", "content": tool_results})
            tool_rounds_run += 1

            # Condition (c): stop after surfacing a tool error to Claude
            if error_occurred:
                break

        # No tool rounds ran → direct response from the first loop iteration
        if tool_rounds_run == 0:
            if not response.content:
                raise ValueError(
                    f"Claude returned an empty response with no content blocks "
                    f"(stop_reason={response.stop_reason!r})."
                )
            return response.content[0].text

        # Condition (b) fired after at least one tool round — the loop's last response
        # is already the final answer; no additional synthesis call needed.
        if response.stop_reason != "tool_use":
            if not response.content:
                raise ValueError(
                    f"Claude returned an empty final response after tool execution "
                    f"(stop_reason={response.stop_reason!r})."
                )
            return response.content[0].text

        # Conditions (a) or (c): loop exhausted MAX_TOOL_ROUNDS or broke on error.
        # Make one explicit synthesis call with tools stripped.
        api_params.pop("tools", None)
        api_params.pop("tool_choice", None)
        final_response = self.client.messages.create(**api_params)
        if not final_response.content:
            raise ValueError(
                f"Claude returned an empty final response after tool execution "
                f"(stop_reason={final_response.stop_reason!r})."
            )
        return final_response.content[0].text