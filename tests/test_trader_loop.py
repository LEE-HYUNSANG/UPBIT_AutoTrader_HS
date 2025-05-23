import pandas as pd
import pytest
from bot.trader import UpbitTrader

class DummyUpbit:
    def __init__(self):
        self.last = None
    def get_balances(self):
        return []
    def buy_market_order(self, ticker, amount):
        self.last = amount
        return {"price": 1000.0, "volume": amount / 1000.0}
    def sell_market_order(self, ticker, qty):
        return {}

def test_buy_market_order_uses_krw(monkeypatch):
    up = DummyUpbit()
    conf = {"amount": 10000, "tickers": ["KRW-TEST"]}
    tr = UpbitTrader("k", "s", conf)
    tr.upbit = up

    df = pd.DataFrame({"open": [1]*120, "high": [1]*120, "low": [1]*120,
                        "close": [1000]*120, "volume": [1]*120})
    monkeypatch.setattr("pyupbit.get_ohlcv", lambda *a, **k: df)
    monkeypatch.setattr("bot.trader.calc_indicators", lambda d: d)
    monkeypatch.setattr("bot.trader.calc_tis", lambda t: 100.0)
    monkeypatch.setattr("bot.trader.df_to_market", lambda d, t: {})
    monkeypatch.setattr("bot.trader.check_buy_signal", lambda s, l, m: True)
    monkeypatch.setattr("bot.trader.check_sell_signal", lambda s, l, m: False)
    monkeypatch.setattr("time.sleep", lambda x: (_ for _ in ()).throw(SystemExit))

    tr.running = True
    with pytest.raises(SystemExit):
        tr.run_loop()
    assert up.last == 10000


def test_failure_limit_warns_but_keeps_ticker():
    tr = UpbitTrader("k", "s", {"tickers": ["KRW-AAA"], "failure_limit": 2})
    tr._record_price_failure("AAA")
    assert "KRW-AAA" in tr.tickers
    tr._record_price_failure("AAA")
    assert "KRW-AAA" in tr.tickers


def test_price_failure_does_not_remove_in_loop(monkeypatch):
    tr = UpbitTrader("k", "s", {"tickers": ["KRW-AAA"], "failure_limit": 1})
    tr._record_price_failure("AAA")
    assert "KRW-AAA" in tr.tickers

    class T:
        t = 0
        @staticmethod
        def time():
            return T.t

    df = pd.DataFrame({"open": [1]*120, "high": [1]*120, "low": [1]*120,
                        "close": [1]*120, "volume": [1]*120})
    monkeypatch.setattr("time.time", T.time)
    monkeypatch.setattr("pyupbit.get_ohlcv", lambda *a, **k: df)
    monkeypatch.setattr("bot.trader.calc_indicators", lambda d: d)
    monkeypatch.setattr("bot.trader.calc_tis", lambda t: 100.0)
    monkeypatch.setattr("bot.trader.df_to_market", lambda d, t: {})
    monkeypatch.setattr("bot.trader.check_buy_signal", lambda s, l, m: False)
    monkeypatch.setattr("bot.trader.check_sell_signal", lambda s, l, m: False)
    monkeypatch.setattr("time.sleep", lambda x: (_ for _ in ()).throw(SystemExit))

    T.t = 2
    tr.running = True
    with pytest.raises(SystemExit):
        tr.run_loop()
    assert "KRW-AAA" in tr.tickers
