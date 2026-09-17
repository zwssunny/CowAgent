"""Deterministic trajectory evaluation scenarios for the Agent tool loop."""

from types import SimpleNamespace

from agent.protocol.agent_stream import AgentStreamExecutor
from agent.tools.base_tool import BaseTool, ToolResult

from tests.trajectory_eval import EvalCase, run_eval_case


class _LookupTool(BaseTool):
    name = "lookup"
    params = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    def __init__(self, results):
        self.results = list(results)

    def execute(self, params):
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _TestAgent:
    def effective_permission_mode(self):
        return "full-access"


class _ScriptedExecutor(AgentStreamExecutor):
    """Drive the real Agent loop with deterministic model responses."""

    def __init__(self, responses, tool, on_event):
        super().__init__(
            agent=_TestAgent(),
            model=SimpleNamespace(model="trajectory-test-model"),
            system_prompt="",
            tools=[tool] if tool else [],
            max_turns=8,
            on_event=on_event,
            messages=[],
        )
        self.responses = list(responses)

    def _is_thinking_enabled(self):
        return False

    def _trim_messages(self):
        return None

    def _validate_and_fix_messages(self):
        return None

    def _call_llm_stream(self, retry_on_empty=True):
        text, tool_calls = self.responses.pop(0)
        content = []
        if text:
            content.append({"type": "text", "text": text})
        content.extend({
            "type": "tool_use",
            "id": call["id"],
            "name": call["name"],
            "input": call.get("arguments", {}),
        } for call in tool_calls)
        self.messages.append({"role": "assistant", "content": content})
        return text, tool_calls, "stop"


def _call(index=1):
    return {
        "id": "lookup-%s" % index,
        "name": "lookup",
        "arguments": {"query": "status"},
    }


def _run(case, responses, results=None):
    tool = _LookupTool(results or []) if results is not None else None

    def make_executor(recorder):
        return _ScriptedExecutor(responses, tool, recorder)

    return run_eval_case(case, make_executor)


def test_direct_answer_has_no_tool_trajectory():
    result = _run(
        EvalCase("direct_answer", "Say hello"),
        [("Hello", [])],
    )

    assert result.final_status == "done"
    assert result.turn_count == 1
    assert result.tool_call_count == 0
    assert result.selected_tools == []


def test_successful_tool_call_is_recorded():
    result = _run(
        EvalCase("successful_tool_call", "Look up status", ("lookup",)),
        [("", [_call()]), ("Status is ready", [])],
        [ToolResult.success("ready")],
    )

    assert result.final_status == "done"
    assert result.turn_count == 2
    assert result.tool_call_count == 1
    assert result.successful_tool_calls == 1
    assert result.failed_tool_calls == 0
    assert result.selected_tools == ["lookup"]


def test_failed_tool_call_is_distinguished_from_runtime_error():
    result = _run(
        EvalCase("failed_tool_call", "Look up status"),
        [("", [_call()]), ("I could not look it up", [])],
        [ToolResult.fail("service unavailable")],
    )

    assert result.final_status == "done"
    assert result.tool_call_count == 1
    assert result.successful_tool_calls == 0
    assert result.failed_tool_calls == 1
    assert result.error_count == 0


def test_recorder_handles_incomplete_tool_events():
    from tests.trajectory_eval import TrajectoryRecorder

    recorder = TrajectoryRecorder()
    recorder({"type": "turn_start", "timestamp": 1, "data": {"turn": 1}})
    recorder({
        "type": "tool_execution_start",
        "timestamp": 2,
        "data": {"tool_call_id": "unfinished", "tool_name": "lookup"},
    })

    result = recorder.result("incomplete")
    assert result.final_status == "incomplete"
    assert result.tool_call_count == 1
    assert result.failed_tool_calls == 0
