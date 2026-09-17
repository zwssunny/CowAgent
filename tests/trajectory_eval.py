"""Small, deterministic helpers for evaluating Agent execution trajectories.

The evaluator consumes the existing AgentStreamExecutor event callback.  It is
intentionally test-only: it does not change runtime behavior or persist data.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Tuple


@dataclass
class EvalCase:
    """A deterministic scenario and the outcome it should produce."""

    name: str
    user_message: str
    expected_tools: Tuple[str, ...] = ()
    expected_status: str = "done"


@dataclass
class EvaluationResult:
    """Metrics collected from one Agent execution."""

    case_name: str
    final_status: str
    turn_count: int
    tool_call_count: int
    successful_tool_calls: int
    failed_tool_calls: int
    selected_tools: List[str]
    error_count: int
    duration_ms: float
    final_response: str = ""
    error: str = ""
    events: List[Dict[str, Any]] = field(default_factory=list, repr=False)


class TrajectoryRecorder:
    """Collect Agent events and turn them into stable, testable metrics."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def __call__(self, event: Dict[str, Any]) -> None:
        if isinstance(event, dict):
            self.events.append(event)

    def result(
        self,
        case_name: str,
        final_response: str = "",
        error: str = "",
    ) -> EvaluationResult:
        starts = []
        ends = []
        runtime_errors = 0
        cancelled = False

        for event in self.events:
            event_type = event.get("type")
            data = event.get("data") or {}
            if event_type == "tool_execution_start":
                starts.append(data)
            elif event_type == "tool_execution_end":
                ends.append(data)
            elif event_type == "error":
                runtime_errors += 1
            elif event_type in ("agent_cancelled", "cancel"):
                cancelled = True

        if cancelled:
            status = "cancelled"
        elif error or runtime_errors:
            status = "error"
        elif any(event.get("type") == "agent_end" for event in self.events):
            status = "done"
        else:
            status = "incomplete"

        timestamps = [
            event.get("timestamp")
            for event in self.events
            if isinstance(event.get("timestamp"), (int, float))
        ]
        duration_ms = 0.0
        if len(timestamps) >= 2:
            duration_ms = max(0.0, (max(timestamps) - min(timestamps)) * 1000)

        selected_tools = []
        for data in starts:
            name = data.get("tool_name")
            if name and name not in selected_tools:
                selected_tools.append(name)

        successful = sum(data.get("status") == "success" for data in ends)
        failed = sum(data.get("status") != "success" for data in ends)
        return EvaluationResult(
            case_name=case_name,
            final_status=status,
            turn_count=sum(event.get("type") == "turn_start" for event in self.events),
            tool_call_count=len({
                data.get("tool_call_id")
                for data in starts + ends
                if data.get("tool_call_id")
            }),
            successful_tool_calls=successful,
            failed_tool_calls=failed,
            selected_tools=selected_tools,
            error_count=runtime_errors,
            duration_ms=duration_ms,
            final_response=final_response or "",
            error=error,
            events=list(self.events),
        )


def run_eval_case(case: EvalCase, executor_factory: Callable) -> EvaluationResult:
    """Run one case without letting a runtime exception hide its trajectory."""

    recorder = TrajectoryRecorder()
    executor = executor_factory(recorder)
    response = ""
    error = ""
    try:
        response = executor.run_stream(case.user_message)
    except Exception as exc:  # The result should make failed runs inspectable.
        error = str(exc)
    return recorder.result(case.name, response, error)
