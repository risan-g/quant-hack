"""Human-readable execution ticket formatting."""

from __future__ import annotations

from quantbot.execution.models import ExecutionPlan


def format_manual_ticket(plan: ExecutionPlan) -> str:
    lines = [
        "# Manual MT5 Execution Ticket",
        "",
        f"- Timestamp: `{plan.timestamp}`",
        f"- Equity: `${plan.equity_usd:,.2f}`",
        f"- Gross leverage state: `{plan.gross_leverage:.2f}x`",
        f"- Gross order notional: `${plan.gross_notional_usd:,.2f}`",
        f"- Orders: `{len(plan.orders)}`",
        "",
        "## Pre-Trade Gates",
        "",
        "- Tiny EURUSD 0.01 open-close test has succeeded.",
        "- MT5 Trade tab is flat unless this ticket intentionally modifies an existing net position.",
        "- MT5 netting mode keeps one net position per symbol.",
        "- Ticket timestamp and data source are understood before entry.",
        "- If MT5 says `market closed`, stop and wait; do not repeatedly retry.",
        "",
        "## Orders",
        "",
    ]
    if not plan.orders:
        lines.append("No orders.")
        return "\n".join(lines)

    for index, order in enumerate(plan.orders, start=1):
        volume = "UNKNOWN" if order.volume_lots is None else f"{order.volume_lots:.2f}"
        lines.extend(
            [
                f"### {index}. {order.symbol}",
                "",
                f"- Action: `{order.side.value.upper()}`",
                f"- MT5 volume: `{volume}` lots",
                f"- Order type: `{order.order_type.value}`",
                f"- Target notional: `${order.notional_usd:,.2f}`",
                f"- Target leverage: `{order.target_leverage:.2f}x`",
                f"- Reason: {order.reason}",
                "",
            ]
        )

    lines.extend(
        [
            "## MT5 Entry Steps",
            "",
            "For each order:",
            "",
            "1. Select the symbol in Market Watch.",
            "2. Open New Order.",
            "3. Set Type to Market Execution.",
            "4. Enter the MT5 volume exactly as shown.",
            "5. Confirm symbol, side, and volume before clicking Buy/Sell.",
            "6. After all orders, verify the Trade tab positions match this ticket.",
            "",
            "MT5 netting mode keeps one net position per symbol. Opposite-side orders can reduce, close, or flip that net position.",
            "",
            "If trading is disabled server-side, do not retry repeatedly. Wait for the official launch window.",
        ]
    )
    return "\n".join(lines)
