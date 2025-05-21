"""Strategy priority and conflict resolution utilities."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from helpers.strategies import check_buy_signal


def active_strategies(strategies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return active strategies sorted by priority."""
    return sorted(
        [s for s in strategies if s.get("active")],
        key=lambda s: s.get("priority", 9999),
    )


def select_buy_strategy(
    market: Dict[str, Any], strategies: List[Dict[str, Any]]
) -> Optional[str]:
    """Return the highest priority strategy with a buy signal."""
    for s in active_strategies(strategies):
        name = s.get("name")
        level = s.get("buy_condition", "중도적")
        if check_buy_signal(name, level, market):
            return name
    return None


_SIGNAL_ORDER = ["ban", "avoid", "sell", "buy", "wait"]


def resolve_signal(flags: Dict[str, bool]) -> str:
    """Return highest priority signal from flag mapping."""
    for key in _SIGNAL_ORDER:
        if flags.get(key):
            return key
    return "wait"

__all__ = [
    "active_strategies",
    "select_buy_strategy",
    "resolve_signal",
]
