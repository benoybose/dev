from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    DENY = "deny"
    CANCEL = "cancel"


@dataclass(frozen=True)
class ApprovalRequest:
    run_id: str
    action: str
    target: str
    reason: str


ApprovalHandler = Callable[[ApprovalRequest], ApprovalDecision | bool]


class ApprovalManager:
    """Single approval boundary used by every mutating tool."""

    def __init__(self, handler: ApprovalHandler | None = None):
        self.handler = handler
        self.requests: list[ApprovalRequest] = []

    def ask(self, request: ApprovalRequest) -> ApprovalDecision:
        self.requests.append(request)
        if self.handler is None:
            return ApprovalDecision.DENY
        decision = self.handler(request)
        if isinstance(decision, bool):
            return ApprovalDecision.APPROVE if decision else ApprovalDecision.DENY
        return decision

    def allows(self, run_id: str, action: str, target: str, reason: str = "") -> bool:
        return self.ask(ApprovalRequest(run_id, action, target, reason)) == ApprovalDecision.APPROVE
