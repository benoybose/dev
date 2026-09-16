from __future__ import annotations

from collections.abc import Callable
from typing import Any

from devx.harness.tools import WorkspaceTools
from devx.llm import create_llm


class AgentDependencyError(RuntimeError):
    pass


def build_coding_agent(settings: Any, tools: WorkspaceTools, approve: Callable[[str, str, str], bool] | None = None):
    """Build a LangChain tool-calling agent with safe mutation gates."""
    try:
        from langchain.agents import create_agent
        from langchain.tools import tool
    except ImportError as exc:
        raise AgentDependencyError("Install the agent extra: pip install 'devx-coding-agent[agent]'") from exc

    def allowed(action: str, target: str, reason: str = "") -> bool:
        return bool(approve and approve(action, target, reason))

    @tool
    def read_file(path: str) -> str:
        """Read a UTF-8 text file inside the workspace."""
        return tools.read(path).output

    @tool
    def search_files(query: str, path: str = ".") -> str:
        """Search text files inside the workspace."""
        return tools.search(query, path).output

    @tool
    def write_file(path: str, content: str) -> str:
        """Write a file after the user approves the exact path."""
        if not allowed("write", path, "Proposed content:\n" + content[:4000]):
            return "WRITE DENIED: request user approval before changing this file."
        return tools.write(path, content, approved=True).output

    @tool
    def replace_in_file(path: str, old_text: str, new_text: str, expected_hash: str = "") -> str:
        """Apply one exact replacement, refusing ambiguous or concurrently changed files."""
        if not allowed("write", path, "Proposed patch:\n" + old_text[:1500] + " -> " + new_text[:1500]):
            return "PATCH DENIED: request user approval before changing this file."
        return tools.replace(path, old_text, new_text, expected_hash=expected_hash or None, approved=True).output

    @tool
    def run_command(command: str) -> str:
        """Run a project command after explicit user approval."""
        if not allowed("command", command, "The agent requested this project command."):
            return "COMMAND DENIED: request user approval before executing this command."
        return tools.run(command, approved=True).output

    return create_agent(model=create_llm(settings), tools=[read_file, search_files, write_file, replace_in_file, run_command],
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
