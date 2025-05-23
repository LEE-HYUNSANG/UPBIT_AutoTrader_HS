import re
from typing import Any, Dict
import pandas as pd
from strategy_loader import load_strategies

# Risk level mapping for convenience
RISK_LEVELS = {"공격적": 0, "중도적": 1, "보수적": 2, "aggressive": 0, "moderate": 1, "conservative": 2}


def _normalize(formula: str) -> str:
    """지표 호출을 DataFrame 컬럼 이름으로 정리한다."""

    def _repl_ma_atr(match: re.Match) -> str:
        atr_period, ma_period = match.group(1), match.group(2)
        return f"ATR{atr_period}_MA{ma_period}"

    def _repl_multi(match: re.Match) -> str:
        name, period, offset = match.group(1), match.group(2), match.group(3)
        result = f"{name}{period}"
        if offset:
            off = abs(int(offset))
            if off:
                result += "_prev" + (str(off) if off > 1 else "")
        return result

    def _repl_bb(match: re.Match) -> str:
        name = match.group(1)
        offset = match.group(2)
        result = name
        if offset:
            off = abs(int(offset))
            if off:
                result += "_prev" + (str(off) if off > 1 else "")
        return result

    def _repl_offset(match: re.Match) -> str:
        col, off = match.group(1), int(match.group(2))
        result = col
        if off != 0:
            off = abs(off)
            result += "_prev" + (str(off) if off > 1 else "")
        return result

    def _repl_single(match: re.Match) -> str:
        name, period = match.group(1), match.group(2)
        return f"{name}{period}"

    # MA(ATR(14),7) 형태 변환
    formula = re.sub(r"MA\(ATR\((\d+)\),\s*(\d+)\)", _repl_ma_atr, formula)

    # MA(Vol,20) -> Vol_MA20 변환
    formula = re.sub(r"MA\((\w+),\s*(\d+)\)", r"\1_MA\2", formula)

    # 볼린저밴드 처리
    formula = re.sub(r"(BB_(?:upper|lower))\(\d+,\s*\d+(?:,\s*(-?\d+))?\)", _repl_bb, formula)


    # 두 개의 인자를 가진 지표 처리 (예: MFI(14,-1))
    formula = re.sub(r"([A-Za-z_]+)\((\d+),\s*(-?\d+)\)", _repl_multi, formula)

    # 단일 인자 지표 처리 먼저 수행 (예: EMA(20))
    indicators = "|".join([
        "EMA",
        "ATR",
        "RSI",
        "MFI",
        "ADX",
        "CCI",
        "StochK",
        "StochD",
        "Tenkan",
        "Kijun",
    ])
    pattern_single = rf"\b({indicators})\(([1-9]\d*)\)"
    formula = re.sub(pattern_single, _repl_single, formula)

    # 오프셋 컬럼 변환 (예: Close(1), PSAR(-2))
    formula = re.sub(r"(\b[A-Za-z_][A-Za-z0-9_]*)\((-?\d+)\)", _repl_offset, formula)

    # Vol 컬럼은 Volume 으로 변경하되 이동평균은 예외
    formula = re.sub(r"\bVol(?!_MA\d+)(?=\b|_)", "Volume", formula)

    return formula


def _apply_shifts(df: pd.DataFrame, formula: str) -> pd.DataFrame:
    """Create shifted columns referenced in the formula."""
    df = df.copy()
    for base, direction, num in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)_(prev|next)(\d*)", formula):
        offset = int(num or 1)
        col_name = f"{base}_{direction}{offset if offset > 1 else ''}"
        if col_name in df.columns or base not in df.columns:
            continue
        if direction == "prev":
            df[col_name] = df[base].shift(offset)
        else:
            df[col_name] = df[base].shift(-offset)
    return df


def evaluate_buy_signals(df: pd.DataFrame, strategy: Dict[str, Any], risk_level: Any) -> pd.Series:
    level_idx = RISK_LEVELS.get(risk_level, risk_level)
    levels = strategy.get('buy_formula_levels')
    if levels:
        formula = levels[level_idx]
    else:
        formula = strategy.get('buy_formula', '')
    expr = formula.replace(' and ', ' & ').replace(' or ', ' | ')
    expr = _normalize(expr)
    df = _apply_shifts(df, expr)
    return df.eval(expr, engine='python').astype(bool)


def df_to_market(df: pd.DataFrame, tis: float) -> Dict[str, Any]:
    return {"df": df.copy(), "tis": tis}


_SPEC_CACHE = load_strategies()


def evaluate_sell_signals(
    df: pd.DataFrame,
    strategy: Dict[str, Any],
    risk_level: Any,
    entry: float,
    peak: float,
) -> pd.Series:
    """매도 전략 포뮬러를 평가한다."""
    level_idx = RISK_LEVELS.get(risk_level, risk_level)
    levels = strategy.get("sell_formula_levels")
    if levels:
        formula = levels[level_idx]
    else:
        formula = strategy.get("sell_formula", "")
    expr = formula.replace(" and ", " & ").replace(" or ", " | ")
    expr = _normalize(expr)
    df = _apply_shifts(df, expr)
    df = df.copy()
    df["Entry"] = entry
    df["EntryPrice"] = entry  # 레거시 포뮬러 호환용
    df["Peak"] = peak
    return df.eval(expr, engine="python").astype(bool)


def check_buy_signal(strategy_name: str, level: str, market: Dict[str, Any]) -> bool:
    """전략명과 시장 데이터로 매수 신호를 계산한다."""
    spec = _SPEC_CACHE.get(strategy_name)
    if not spec:
        return False
    res = evaluate_buy_signals(
        market["df"],
        {"buy_formula_levels": spec.buy_formula_levels},
        level,
    )
    return bool(res.iloc[-1])


def check_sell_signal(strategy_name: str, level: str, market: Dict[str, Any]) -> bool:
    """전략명과 시장 데이터로 매도 신호를 계산한다."""
    spec = _SPEC_CACHE.get(strategy_name)
    if not spec:
        return False
    entry = market.get("Entry")
    if entry is None:
        entry = market.get("EntryPrice", 0.0)
    peak = market.get("Peak", market["df"]["High"].cummax().iloc[-1])
    res = evaluate_sell_signals(
        market["df"],
        {"sell_formula_levels": spec.sell_formula_levels},
        level,
        entry,
        peak,
    )
    return bool(res.iloc[-1])
