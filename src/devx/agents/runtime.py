from __future__ import annotations

from collections.abc import Callable
from typing import Any

from devx.harness.mcp import register_mcp_servers
from devx.harness.tool_registry import ToolRegistry, ToolSpec, load_plugins
from devx.harness.tools import WorkspaceTools
from devx.llm import create_llm


class AgentDependencyError(RuntimeError):
    pass


class AgentToolLimitExceeded(RuntimeError):
    """Raised when a model attempts more tool calls than the configured limit."""


def build_tool_registry(settings: Any) -> ToolRegistry:
    """Load explicitly configured plugins and MCP tools for one agent run."""
    registry = ToolRegistry()
    load_plugins(settings.workspace, tuple(getattr(settings, "plugin_paths", ())), registry)
    register_mcp_servers(settings.workspace, tuple(getattr(settings, "mcp_servers", ())), registry)
    return registry


def build_coding_agent(settings: Any, tools: WorkspaceTools,
                       approve: Callable[[str, str, str], bool] | None = None,
                       tool_call_budget: Callable[[], None] | None = None,
                       registry: ToolRegistry | None = None):
    """Build a LangChain tool-calling agent with safe mutation gates."""
    try:
        from langchain.agents import create_agent
        from langchain.tools import tool
    except ImportError as exc:
        raise AgentDependencyError("Install the agent extra: pip install 'devx-coding-agent[agent]'") from exc

    max_tool_calls = max(1, int(getattr(settings, "max_tool_calls", 40)))
    call_count = 0

    def consume_local_tool_call() -> None:
        tools.cancellation.raise_if_cancelled()
        nonlocal call_count
        call_count += 1
        if call_count > max_tool_calls:
            raise AgentToolLimitExceeded(f"Tool-call limit exceeded ({max_tool_calls})")

    consume_tool_call = tool_call_budget or consume_local_tool_call

    def allowed(action: str, target: str, reason: str = "") -> bool:
        return bool(approve and approve(action, target, reason))

    @tool
    def read_file(path: str) -> str:
        """Read a UTF-8 text file inside the workspace."""
        consume_tool_call()
        return tools.read(path).output

    @tool
    def search_files(query: str, path: str = ".") -> str:
        """Search text files inside the workspace."""
        consume_tool_call()
        return tools.search(query, path).output

    @tool
    def write_file(path: str, content: str) -> str:
        """Write a file after the user approves the exact path."""
        consume_tool_call()
        preview = tools.preview_write(path, content)
        if tools.requires_approval("edit", path) and not allowed("write", path, "Proposed diff:\n" + preview):
            tools.cancellation.raise_if_cancelled()
            return "WRITE DENIED: request user approval before changing this file."
        return tools.write(path, content, approved=True).output

    @tool
    def replace_in_file(path: str, old_text: str, new_text: str, expected_hash: str = "") -> str:
        """Apply one exact replacement, refusing ambiguous or concurrently changed files."""
        consume_tool_call()
        preview = tools.preview_replace(path, old_text, new_text)
        if tools.requires_approval("edit", path) and not allowed("write", path, "Proposed diff:\n" + preview):
            tools.cancellation.raise_if_cancelled()
            return "PATCH DENIED: request user approval before changing this file."
        return tools.replace(path, old_text, new_text, expected_hash=expected_hash or None, approved=True).output

    @tool
    def run_command(command: str) -> str:
        """Run a project command after explicit user approval."""
        consume_tool_call()
        if tools.requires_approval("shell", command) and not allowed("command", command, "The agent requested this project command."):
            tools.cancellation.raise_if_cancelled()
            return "COMMAND DENIED: request user approval before executing this command."
        return tools.run(command, approved=True).output

    registry = registry or build_tool_registry(settings)
    builtins = {
        "read_file": read_file,
        "search_files": search_files,
        "write_file": write_file,
        "replace_in_file": replace_in_file,
        "run_command": run_command,
    }
    for name, tool_object in builtins.items():
        if name not in registry.names():
            registry.register_object(name, tool_object)

    def before_extension_call(spec: ToolSpec, arguments: dict[str, Any]) -> str | None:
        consume_tool_call()
        action = spec.permission_action
        if not action:
            return None
        target = spec.approval_target
        if callable(target):
            target = target(arguments)
        target = str(target or spec.name)
        if tools.requires_approval(action, target) and not allowed(
            action, target, f"The tool {spec.name!r} requested an external action."
        ):
            tools.cancellation.raise_if_cancelled()
            return f"{spec.name.upper()} DENIED: request user approval before using this tool."
        return None

    return create_agent(model=create_llm(settings), tools=registry.langchain_tools(before_extension_call),
                        system_prompt=("You are a careful coding agent. Inspect before editing, make minimal changes, "
                                       "explain intended mutations, and run focused tests after approved edits. "
                                       "Never claim a denied action succeeded."))


async def stream_agent_events(agent: Any, messages: list[dict[str, str]], callback: Callable[[dict[str, Any]], None] | None = None):
    """Yield LangChain v2 event records and optionally forward them to a UI."""
    async for event in agent.astream_events({"messages": messages}, version="v2"):
        if callback:
            callback(event)
        yield event


def stream_agent_text(agent: Any, messages: list[dict[str, str]], callback: Callable[[dict[str, Any]], None] | None = None) -> str:
    """Synchronously stream AI message chunks for supervisor worker threads."""
    chunks: list[str] = []
    try:
        updates = agent.stream({"messages": messages}, stream_mode="messages")
        for item in updates:
            message = item[0] if isinstance(item, tuple) else item
            if getattr(message, "type", "ai") not in {"ai", "AIMessageChunk"}:
                continue
            content = getattr(message, "content", "")
            if isinstance(content, list):
                content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
            if content:
                text = str(content)
                chunks.append(text)
                if callback:
                    callback({"type": "token", "text": text})
    except (AttributeError, TypeError, RuntimeError):
        return response_text(agent.invoke({"messages": messages}))
    return "".join(chunks)


def response_text(result: dict[str, Any]) -> str:
    messages = result.get("messages", [])
    if not messages:
        return ""
    content = getattr(messages[-1], "content", messages[-1].get("content", "") if isinstance(messages[-1], dict) else "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(item.get("text", str(item)) if isinstance(item, dict) else str(item) for item in content)
    return str(content)
