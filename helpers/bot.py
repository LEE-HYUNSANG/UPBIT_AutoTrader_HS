# -*- coding: utf-8 -*-
"""Simple autonomous trading loop."""

from __future__ import annotations

import json
import logging
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Callable, Any

import pyupbit

from utils import load_filter_settings, load_market_signals, load_secrets, send_telegram
from helpers.strategies import check_buy_signal, check_sell_signal, df_to_market
from helpers.priorities import select_buy_strategy
from helpers.utils.strategy_cfg import load_strategy_list
from helpers.execution import smart_buy, smart_sell
from helpers.logger import log_trade
from helpers.utils.funds import load_fund_settings
from helpers.utils.risk import (
    load_risk_settings,
    load_manual_sells,
    save_manual_sells,
)

logger = logging.getLogger(__name__)

try:
    _SEC = load_secrets()
    _TOKEN = _SEC.get("TELEGRAM_TOKEN")
    _CHAT = _SEC.get("TELEGRAM_CHAT_ID")
except Exception:  # pragma: no cover - secrets load
    _TOKEN = os.getenv("TELEGRAM_TOKEN")
    _CHAT = os.getenv("TELEGRAM_CHAT_ID")


def _alert(msg: str) -> None:
    """텔레그램과 로그로 오류를 알린다."""
    logger.error(msg)
    if _TOKEN and _CHAT:
        try:
            send_telegram(_TOKEN, _CHAT, msg)
        except Exception:  # pragma: no cover - network
            logger.debug("telegram send failed")

# 포지션 변경 시 동시 접근을 방지하기 위한 락
_LOCK = threading.Lock()
BALANCE_CACHE: list = []


def _safe_call(
    func: Callable[..., Any],
    *args: Any,
    retries: int = 3,
    delay: float = 0.5,
    **kwargs: Any,
) -> Any:
    """Retry ``func`` up to ``retries`` times with exponential backoff."""
    for attempt in range(retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - runtime
            log_trade("ERROR", {"func": func.__name__, "error": str(exc)})
            logger.warning("%s retry %s/%s", func.__name__, attempt + 1, retries)
            _alert(f"[API Exception] {func.__name__} 오류: {exc}")
            time.sleep(delay)
            delay *= 2
    _alert(f"[ERROR] {func.__name__} 호출 실패")
    raise


def refresh_positions(upbit: pyupbit.Upbit, active: Dict[str, Dict[str, float]]) -> None:
    """현재 잔고 정보를 읽어 포지션을 동기화한다."""
    balances = _safe_call(upbit.get_balances)
    updated: Dict[str, Dict[str, float]] = {}
    for b in balances:
        if b.get("currency") == "KRW":
            continue
        qty = float(b.get("balance", 0))
        if qty <= 0:
            continue
        ticker = f"KRW-{b['currency']}"
        updated[ticker] = {
            "buy_price": float(b.get("avg_buy_price", 0)),
            "qty": qty,
            "strategy": active.get(ticker, {}).get("strategy", "INIT"),
            "level": active.get(ticker, {}).get("level", "중도적"),
        }
    with _LOCK:
        active.clear()
        active.update(updated)
        BALANCE_CACHE[:] = balances
    log_trade("REFRESH", {"count": len(updated)})
    logger.info("[BOT] positions refreshed %d", len(updated))


def load_strategy_settings(path: str = "config/strategy.json") -> Dict[str, str]:
    """Read strategy settings or fallback to config.json."""
    defaults = {"strategy": "M-BREAK", "level": "중도적"}
    file_path = path if os.path.exists(path) else "config/config.json"
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
        defaults["strategy"] = data.get("strategy", defaults["strategy"])
        defaults["level"] = data.get("level", defaults["level"])
    except Exception:
        logger.warning("Failed to load strategy settings from %s", file_path)
    return defaults


def get_filtered_tickers(filter_conf: Dict[str, float]) -> list[str]:
    """Return list of KRW tickers filtered by price and rank."""
    min_p = float(filter_conf.get("min_price", 0) or 0)
    max_p = float(filter_conf.get("max_price", 0) or 0)
    rank = int(filter_conf.get("rank", 0) or 0)
    signals = load_market_signals()
    tickers: list[str] = []
    for s in signals:
        price = float(s.get("price", 0))
        if min_p and price < min_p:
            continue
        if max_p and max_p > 0 and price > max_p:
            continue
        tickers.append(f"KRW-{s.get('coin')}")
        if rank and len(tickers) >= rank:
            break
    return tickers


def run_trading_bot(upbit: pyupbit.Upbit, interval: float = 3.0) -> None:
    """Main trading loop integrating strategy checks and execution."""
    filter_conf = load_filter_settings()
    strategy_conf = load_strategy_settings()
    strategy_table = load_strategy_list()
    fund_conf = load_fund_settings()
    risk_conf = load_risk_settings()
    active_trades: Dict[str, Dict[str, float]] = {}
    try:
        balances = _safe_call(upbit.get_balances)
        with _LOCK:
            BALANCE_CACHE[:] = balances
        for b in balances:
            if b.get("currency") == "KRW":
                continue
            bal = float(b.get("balance", 0))
            if bal <= 0:
                continue
            ticker = f"KRW-{b['currency']}"
            with _LOCK:
                active_trades[ticker] = {
                    "buy_price": float(b.get("avg_buy_price", 0)),
                    "qty": bal,
                    "strategy": "INIT",
                    "level": strategy_conf.get("level", "중도적"),
                }
    except Exception as exc:  # pragma: no cover - runtime
        logger.warning("Failed to preload positions %s", exc)
    last_reload = time.time()
    logger.info("[BOT] starting trading loop")

    executor = ThreadPoolExecutor(
        max_workers=fund_conf.get("max_concurrent_trades", 5)
    )
    next_run = time.time()
    error_count = 0
    while True:
        try:
            now = time.time()
            manual = load_manual_sells()
            manual_update = False
            for m in manual:
                pos = active_trades.get(m)
                if not pos:
                    continue
                avg, vol = _safe_call(
                    smart_sell,
                    upbit,
                    m,
                    pos["qty"],
                    fund_conf.get("slippage_tolerance", 0.001),
                )
                log_trade("SELL", {"ticker": m, "price": avg, "qty": vol})
                logger.info("[BOT] manual sold %s avg=%.8f qty=%.6f", m, avg, vol)
                with _LOCK:
                    active_trades.pop(m, None)
                manual_update = True
            if manual:
                save_manual_sells([])
            if manual_update:
                refresh_positions(upbit, active_trades)
            if now - last_reload > 300:
                filter_conf = load_filter_settings()
                strategy_conf = load_strategy_settings()
                strategy_table = load_strategy_list()
                fund_conf = load_fund_settings()
                risk_conf = load_risk_settings()
                last_reload = now
                logger.info("[BOT] config reloaded")

            filtered = get_filtered_tickers(filter_conf)
            logger.debug("[BOT] tickers %s", filtered)

            buy_tasks = []
            for ticker in filtered:
                if ticker in active_trades:
                    continue
                if len(active_trades) + len(buy_tasks) >= fund_conf.get(
                    "max_concurrent_trades", 1
                ):
                    logger.debug("[BOT] max concurrent trades reached")
                    break
                market = {}
                strat = select_buy_strategy(market, strategy_table)
                if strat:
                    level = next(
                        (s.get("buy_condition", "중도적") for s in strategy_table if s.get("name") == strat),
                        "중도적",
                    )
                    fut = executor.submit(
                        _safe_call,
                        smart_buy,
                        upbit,
                        ticker,
                        fund_conf.get("buy_amount", 0),
                        fund_conf.get("slippage_tolerance", 0.001),
                        slippage_limit=fund_conf.get("slippage_tolerance", 0.001),
                    )
                    buy_tasks.append((ticker, strat, level, fut))

            needs_update = False
            for ticker, strat, level, fut in buy_tasks:
                price, qty = fut.result()
                if qty > 0:
                    with _LOCK:
                        active_trades[ticker] = {
                            "buy_price": price,
                            "qty": qty,
                            "strategy": strat,
                            "level": level,
                        }
                    log_trade("BUY", {"ticker": ticker, "price": price, "qty": qty})
                    logger.info("[BOT] bought %s price=%.8f qty=%.6f", ticker, price, qty)
                    needs_update = True

            sell_tasks = []
            for ticker, pos in list(active_trades.items()):
                if check_sell_signal(
                    pos["strategy"],
                    ticker,
                    pos["buy_price"],
                    pos["level"],
                    risk_conf,
                ):
                    fut = executor.submit(
                        _safe_call,
                        smart_sell,
                        upbit,
                        ticker,
                        pos["qty"],
                        fund_conf.get("slippage_tolerance", 0.001),
                        slippage_limit=fund_conf.get("slippage_tolerance", 0.001),
                    )
                    sell_tasks.append((ticker, fut))

            for ticker, fut in sell_tasks:
                avg, vol = fut.result()
                log_trade("SELL", {"ticker": ticker, "price": avg, "qty": vol})
                logger.info("[BOT] sold %s avg=%.8f qty=%.6f", ticker, avg, vol)
                with _LOCK:
                    active_trades.pop(ticker, None)
                needs_update = True

            if needs_update:
                refresh_positions(upbit, active_trades)

        except Exception as e:  # pragma: no cover - runtime loop
            logger.exception("[BOT] error %s", e)
            _alert(f"[ERROR] 봇 루프 오류: {e}")
            error_count += 1
            if error_count >= 3:
                _alert(f"[ERROR] 연속 {error_count}회 오류 발생")
                error_count = 0
            time.sleep(10)
            next_run = time.time()
            continue
        error_count = 0
        next_run += interval
        sleep = max(0, next_run - time.time())
        time.sleep(sleep)
