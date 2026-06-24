"""Write proposed adjustment orders for MT5 dry-run review."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from quantbot.execution.models import ExecutionPlan, OrderIntent


PROPOSED_ORDER_COLUMNS = [
    "timestamp",
    "symbol",
    "side",
    "volume_lots",
    "order_type",
    "dry_run",
    "reason",
]


def proposed_order_reason(order: OrderIntent) -> str:
    reason = order.reason
    if order.stop_loss_price is not None:
        reason += f"; sl_price={order.stop_loss_price:.10g}"
    if order.take_profit_price is not None:
        reason += f"; tp_price={order.take_profit_price:.10g}"
    return reason


def proposed_orders_frame(plan: ExecutionPlan, dry_run: bool = True) -> pd.DataFrame:
    rows: list[dict[str, str | float | bool]] = []
    for order in plan.orders:
        rows.append(
            {
                "timestamp": plan.timestamp,
                "symbol": order.symbol,
                "side": order.side.value,
                "volume_lots": 0.0 if order.volume_lots is None else order.volume_lots,
                "order_type": order.order_type.value,
                "dry_run": dry_run,
                "reason": proposed_order_reason(order),
            }
        )
    return pd.DataFrame(rows, columns=PROPOSED_ORDER_COLUMNS)


def write_proposed_orders_csv(plan: ExecutionPlan, path: Path, dry_run: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    proposed_orders_frame(plan, dry_run=dry_run).to_csv(path, index=False)
