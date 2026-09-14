from __future__ import annotations

from typing import Any, TypedDict

from dev.agents.runtime import build_coding_agent, response_text, stream_agent_text
from dev.harness.approval import ApprovalManager
from dev.harness.changes import ChangeJournal
from dev.harness.permissions import PermissionPolicy
from dev.harness.runtime import CancellationToken
from dev.harness.session import SessionStore
from dev.harness.testing import detect_test_command
from dev.harness.tools import WorkspaceTools
from dev.llm import create_llm, invoke_with_retry
from dev.token_optim.context import read_context


class GraphState(TypedDict, total=False):
    task: str
    messages: list[dict[str, str]]
    files_in_context: list[str]
    plan: str
    result: str
    test_result: str
    events: list[dict[str, Any]]
    status: str
    active_agent: str
    iteration: int
    test_attempts: int
    repair_attempts: int
    test_command: str
    requested_agent: str


class ConfiguredGraph:
    """Small adapter that supplies a stable LangGraph checkpoint thread ID."""
    def __init__(self, graph: Any, thread_id: str):
        self.graph, self.thread_id = graph, thread_id

    def _config(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        merged = dict(config or {})
        configurable = dict(merged.get("configurable", {}))
        configurable.setdefault("thread_id", self.thread_id)
        merged["configurable"] = configurable
        return merged

    def invoke(self, state: GraphState, config: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.graph.invoke(state, config=self._config(config))

    async def ainvoke(self, state: GraphState, config: dict[str, Any] | None = None) -> dict[str, Any]:
        return await self.graph.ainvoke(state, config=self._config(config))


def build_langgraph_supervisor(settings: Any, approvals: ApprovalManager, files: list[str] | None = None,
                               run_id: str | None = None, session_id: str | None = None,
                               cancellation: CancellationToken | None = None, event_sink: Any = None):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise ImportError("Install the agent extra for LangGraph orchestration") from exc

    import uuid
    run_id = run_id or str(uuid.uuid4())
    cancellation = cancellation or CancellationToken()
    session_store = SessionStore(settings.session_db)
    journal = ChangeJournal(settings.session_db)
    tools = WorkspaceTools(PermissionPolicy(settings.workspace, settings.approval_required),
                           max_bytes=settings.max_file_bytes, timeout=settings.command_timeout,
                           journal=journal, run_id=run_id, cancellation=cancellation)
    paths = files or []
    path_objects = [__import__("pathlib").Path(path) for path in paths]
    embedder = None
    semantic_cache = None
    if settings.embeddings_enabled:
        try:
            from dev.token_optim.cache import SemanticCache, fingerprint_files
            from dev.token_optim.embeddings import LocalEmbedder
            embedder = LocalEmbedder(settings.embedding_model, settings.embedding_cache_dir, settings.embeddings_offline)
            semantic_cache = SemanticCache(settings.cache_db, embedder=embedder)
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            if event_sink:
                event_sink({"type": "embedding_unavailable", "error": str(exc)})
    context = read_context(path_objects, settings.max_file_bytes)
    context_fingerprint = ""
    if semantic_cache:
        from dev.token_optim.cache import fingerprint_files
        context_fingerprint = fingerprint_files(path_objects)

    def emit(state: GraphState, event: dict[str, Any]) -> None:
        state.setdefault("events", []).append(event)
        if event_sink:
            event_sink(event)
        session_store.append_event(session_id or run_id, run_id, event)

    def planner(state: GraphState) -> GraphState:
        cancellation.raise_if_cancelled()
        emit(state, {"type": "agent_started", "agent": "planner"})
        specialist = state.get("requested_agent", "supervisor")
        cached_plan = semantic_cache.get("plan:" + state["task"], context_fingerprint) if semantic_cache else None
        if cached_plan:
            state["plan"] = cached_plan
            emit(state, {"type": "cache_hit", "kind": "plan"})
        else:
            response = invoke_with_retry(create_llm(settings), "Create a concrete coding plan. Do not edit files. "
                                          f"Give special attention to the requested specialist perspective: {specialist}.\n\nTask:\n"
                                          + state["task"] + "\n\nContext:\n" + context)
            state["plan"] = str(getattr(response, "content", response))
            if semantic_cache:
                semantic_cache.set("plan:" + state["task"], state["plan"], context_fingerprint)
        state.setdefault("messages", []).append({"role": "planner", "content": state["plan"]})
        state["active_agent"] = "coder"
        state["iteration"] = state.get("iteration", 0) + 1
        emit(state, {"type": "agent_finished", "agent": "planner"})
        return state

    def approve(action: str, target: str, reason: str = "") -> bool:
        return approvals.allows(run_id, action, target, reason)

    def coder(state: GraphState) -> GraphState:
        cancellation.raise_if_cancelled()
        emit(state, {"type": "agent_started", "agent": "coder"})
        agent = build_coding_agent(settings, tools, approve)
        if state.get("repair_attempts", 0):
            prompt = (
                "The latest test run failed. Inspect the failure, make the smallest approved fix, "
                "and report exactly what changed. Do not weaken or remove tests.\n\nFailure:\n"
                + state.get("test_result", "")
            )
        else:
            prompt = (
                "Execute this approved coding task. Inspect before editing, make minimal changes, "
                "and report exactly what happened.\n\nTask:\n" + state["task"] +
                "\n\nPlan:\n" + state.get("plan", "") + "\n\nContext:\n" + context
            )
        if state.get("requested_agent"):
            prompt += "\n\nRequested specialist perspective: " + state["requested_agent"]
        messages = [{"role": "user", "content": prompt}]
        if event_sink:
            state["result"] = stream_agent_text(agent, messages, lambda event: emit(state, event))
        else:
            state["result"] = response_text(agent.invoke({"messages": messages}))
        state.setdefault("messages", []).append({"role": "coder", "content": state["result"]})
        state["active_agent"] = "tester"
        state["iteration"] = state.get("iteration", 0) + 1
        emit(state, {"type": "agent_finished", "agent": "coder"})
        return state

    def tester(state: GraphState) -> GraphState:
        cancellation.raise_if_cancelled()
        emit(state, {"type": "agent_started", "agent": "tester"})
        command = state.get("test_command") or settings.test_command or detect_test_command(settings.workspace)
        state["test_command"] = command or ""
        state["test_attempts"] = state.get("test_attempts", 0) + 1
        state["iteration"] = state.get("iteration", 0) + 1
        if not command:
            state["test_result"] = "No test command detected."
            state["status"] = "completed"
        elif not approve("command", command, "Detected/configured project test command."):
            state["test_result"] = "Test execution denied by user."
            state["status"] = "completed"
        else:
            result = tools.run(command, approved=True)
            state["test_result"] = result.output or f"exit code: {result.exit_code}"
            state["status"] = "completed" if result.ok else "tests_failed"
            emit(state, {"type": "test_finished", "ok": result.ok, "exit_code": result.exit_code})
            if not result.ok:
                state["repair_attempts"] = state.get("repair_attempts", 0)
        state.setdefault("messages", []).append({"role": "tester", "content": state["test_result"]})
        state["active_agent"] = "supervisor"
        state["status"] = state.get("status", "completed")
        emit(state, {"type": "agent_finished", "agent": "tester"})
        return state

    def route_after_tester(state: GraphState) -> str:
        """Retry failed tests at most twice, subject to the run iteration cap."""
        if state.get("status") != "tests_failed":
            return "finish"
        max_repairs = min(2, max(0, (settings.max_iterations - state.get("iteration", 0)) // 2))
        if state.get("repair_attempts", 0) >= max_repairs:
            return "finish"
        state["repair_attempts"] = state.get("repair_attempts", 0) + 1
        state["active_agent"] = "coder"
        return "repair"

    graph = StateGraph(GraphState)
    graph.add_node("planner", planner)
    graph.add_node("coder", coder)
    graph.add_node("tester", tester)
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "coder")
    graph.add_edge("coder", "tester")
    graph.add_conditional_edges("tester", route_after_tester, {"repair": "coder", "finish": END})
    try:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver
        connection = sqlite3.connect(settings.session_db, check_same_thread=False)
        return ConfiguredGraph(graph.compile(checkpointer=SqliteSaver(connection)), session_id or run_id)
    except (ImportError, TypeError):
        return ConfiguredGraph(graph.compile(), session_id or run_id)
