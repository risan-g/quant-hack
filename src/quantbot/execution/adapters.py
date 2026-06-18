"""Execution adapter interfaces and local manual adapter."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from quantbot.execution.models import ExecutionPlan, ExecutionReceipt


class ExecutionAdapter(ABC):
    @abstractmethod
    def submit(self, plan: ExecutionPlan) -> ExecutionReceipt:
        """Submit an execution plan."""


class ManualExecutionAdapter(ExecutionAdapter):
    """Write an execution ticket for manual, chat, or MT5 hand-entry fallback."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def submit(self, plan: ExecutionPlan) -> ExecutionReceipt:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        safe_timestamp = plan.timestamp.replace(":", "").replace("+", "_").replace("-", "")
        path = self.output_dir / f"manual_ticket_{safe_timestamp}.json"
        path.write_text(json.dumps(plan.model_dump(mode="json"), indent=2), encoding="utf-8")
        return ExecutionReceipt(
            adapter="manual",
            accepted=True,
            message=f"Wrote manual execution ticket to {path}",
            order_count=len(plan.orders),
        )
