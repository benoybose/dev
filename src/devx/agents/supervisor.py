from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from devx.agents.graph import DevxState
from devx.agents.runtime import build_coding_agent, response_text, stream_agent_text
from devx.harness.approval import ApprovalManager
from devx.harness.changes import ChangeJournal
from devx.harness.permissions import PermissionPolicy
from devx.harness.runtime import CancellationToken, RunCancelled
from devx.harness.session import SessionStore
from devx.harness.testing import detect_test_command
from devx.harness.tools import WorkspaceTools
from devx.llm import invoke_with_retry
from devx.token_optim.context import read_context


@dataclass
class SupervisorRunner:
    settings: Any
    approvals: ApprovalManager
    run_id: str = "run"
    cancellation: CancellationToken | None = None
    event_sink: Any = None
    session_id: str | None = None

    def __post_init__(self) -> None:
        policy = PermissionPolicy(self.settings.workspace, self.settings.approval_required)
        journal = ChangeJournal(self.settings.session_db)
        self.sessions = SessionStore(self.settings.session_db)
        self.cancellation = self.cancellation or CancellationToken()
        self.tools = WorkspaceTools(policy, max_bytes=self.settings.max_file_bytes,
                                    timeout=self.settings.command_timeout, run_id=self.run_id, journal=journal,
                                    cancellation=self.cancellation)

    def _event(self, state: DevxState, event: dict[str, Any]) -> None:
        state.events.append(event)
        self.sessions.append_event(self.session_id or self.run_id, self.run_id, event)
        if self.event_sink:
            self.event_sink(event)

    def _approve(self, action: str, target: str, reason: str = "") -> bool:
        return self.approvals.allows(self.run_id, action, target, reason)

    def __call__(self, state: DevxState) -> DevxState:
        state.status = "running"
        try:
            self.cancellation.raise_if_cancelled()
            self._event(state, {"type": "agent_started", "agent": "planner"})
            from devx.llm import create_llm
            model = create_llm(self.settings)
            context = read_context([__import__("pathlib").Path(path) for path in state.files_in_context], self.settings.max_file_bytes)
            plan_response = invoke_with_retry(model, 
                "Create a concise, concrete coding plan. Identify files, intended changes, and tests. "
                "Do not edit files.\n\nTask:\n" + state.task + "\n\nContext:\n" + context
            )
            plan = getattr(plan_response, "content", str(plan_response))
            self._event(state, {"type": "agent_finished", "agent": "planner"})
            state.messages.append({"role": "planner", "content": str(plan)})
            state.active_agent = "coder"
            state.iteration += 1

            self.cancellation.raise_if_cancelled()
            self._event(state, {"type": "agent_started", "agent": "coder"})
            coder = build_coding_agent(self.settings, self.tools, self._approve)
            coding_messages = [{"role": "user", "content": (
                "Execute this coding task using the available tools. Inspect first, make minimal approved edits, "
                "and report exactly what happened.\n\nTask:\n" + state.task + "\n\nPlan:\n" + str(plan) + "\n\nContext:\n" + context
            )}]
            if self.event_sink:
                coding_text = stream_agent_text(coder, coding_messages, lambda event: self._event(state, event))
                coding = {"messages": [{"content": coding_text}]}
            else:
                coding = coder.invoke({"messages": coding_messages})
            state.messages.append({"role": "coder", "content": response_text(coding)})
            self._event(state, {"type": "agent_finished", "agent": "coder"})
            state.active_agent = "tester"
            state.iteration += 1

            self.cancellation.raise_if_cancelled()
            self._event(state, {"type": "agent_started", "agent": "tester"})
            test_result = "No test command configured."
            test_command = self.settings.test_command or detect_test_command(self.settings.workspace)
            if test_command:
                if self._approve("command", test_command, "Detected/configured project test command."):
                    result = self.tools.run(test_command, approved=True)
                    test_result = result.output or f"exit code: {result.exit_code}"
                    self._event(state, {"type": "test_finished", "ok": result.ok, "exit_code": result.exit_code})
                    # Give the coder a bounded opportunity to repair a failing test run.
                    for _ in range(max(0, min(2, self.settings.max_iterations - state.iteration))):
                        if result.ok:
                            break
                        state.active_agent = "coder"
                        state.iteration += 1
                        repair = coder.invoke({"messages": [{"role": "user", "content": (
                            "The test command failed. Inspect the failure, make a minimal approved fix, "
                            "and report the change.\n\nFailure:\n" + test_result
                        )}]})
                        state.messages.append({"role": "coder", "content": response_text(repair)})
                        result = self.tools.run(test_command, approved=True)
                        test_result = result.output or f"exit code: {result.exit_code}"
                    if not result.ok:
                        state.status = "tests_failed"
                else:
                    test_result = "Test execution denied by user."
            state.messages.append({"role": "tester", "content": test_result})
            self._event(state, {"type": "agent_finished", "agent": "tester"})
            state.active_agent = "supervisor"
            if state.status != "tests_failed":
                state.status = "completed"
            state.result = response_text(coding) + "\n\nTests:\n" + test_result
        except RunCancelled as exc:
            state.status = "cancelled"
            self._event(state, {"type": "cancelled"})
            state.result = str(exc)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            state.status = "failed"
            self._event(state, {"type": "error", "error": str(exc)})
            state.result = f"Agent run failed: {exc}"
        return state


DevState = DevxState
