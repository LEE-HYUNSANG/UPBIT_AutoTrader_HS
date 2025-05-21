import types
from helpers import priorities


def test_active_strategies_sorting():
    data = [
        {"name": "B", "active": True, "priority": 2},
        {"name": "A", "active": True, "priority": 1},
        {"name": "C", "active": False, "priority": 0},
    ]
    res = priorities.active_strategies(data)
    assert [s["name"] for s in res] == ["A", "B"]


def test_select_buy_strategy(monkeypatch):
    calls = []

    def fake_check(name, level, market):
        calls.append(name)
        return name == "B"

    monkeypatch.setattr(priorities, "check_buy_signal", fake_check)
    data = [
        {"name": "A", "active": True, "buy_condition": "중도적", "priority": 2},
        {"name": "B", "active": True, "buy_condition": "중도적", "priority": 1},
    ]
    sel = priorities.select_buy_strategy({}, data)
    assert sel == "B"
    assert calls == ["B"]


def test_resolve_signal():
    flags = {"buy": True, "avoid": True}
    assert priorities.resolve_signal(flags) == "avoid"
    flags = {"wait": True}
    assert priorities.resolve_signal(flags) == "wait"
