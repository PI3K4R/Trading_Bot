"""Unit tests for fetching_data adapters (mocked exchange clients / HTTP)."""

from datetime import datetime
from unittest.mock import MagicMock
import pandas as pd
import pytest
import config as cfg
import fetching_data as fd

FIXED_NOW = datetime(2024, 1, 1, 12, 0, 5, tzinfo=cfg.TIMEZONE)
FIXED_NOW_ts = int(FIXED_NOW.timestamp()) * 1000


def _assert_candle_keys(candle: dict, *, closed_key: str = "is_closed") -> None:
    assert set(candle) >= {
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        closed_key,
    }
    assert isinstance(candle["open_time"], datetime)
    assert candle["open_time"].tzinfo is not None
    for key in ("open", "high", "low", "close", "volume"):
        assert isinstance(candle[key], float)


def _assert_order_book_meta(result: dict, *, exchange: str, symbol: str, depth: int) -> None:
    assert result["exchange"] == exchange
    assert result["symbol"] == symbol
    assert result["depth"] == depth
    assert isinstance(result["sampled_at"], datetime)
    assert result["minute_bucket"] == result["sampled_at"].replace(second=0, microsecond=0)
    assert "order_book" in result


# --- Candles -----------------------------------------------------------------


def test_fetch_candles_binance_maps_fields_and_defaults(patch_datetime_now):
    open = FIXED_NOW_ts - 60000
    close = FIXED_NOW_ts - 1000
    client = MagicMock()
    client.get_historical_klines.return_value = [
        [open, "1", "2", "0.5", "1.5", "10", close, 0, 0, 0, 0, 0]
    ]

    result = fd.fetch_candles_binance(client, symbol="BTCUSDT")

    assert result["exchange"] == "Binance"
    assert result["interval"] == "1m"
    assert len(result["candles"]) == 1
    candle = result["candles"][0]
    _assert_candle_keys(candle)
    assert candle["open"] == 1.0
    assert candle["high"] == 2.0
    assert candle["low"] == 0.5
    assert candle["close"] == 1.5
    assert candle["volume"] == 10.0
    assert candle["is_closed"] is True
    assert candle["close_time"] == datetime.fromtimestamp(close / 1000, tz=cfg.TIMEZONE)

    kwargs = client.get_historical_klines.call_args.kwargs
    assert kwargs["symbol"] == "BTCUSDT"
    assert int(kwargs["end_str"]) == FIXED_NOW_ts
    assert int(kwargs["start_str"]) == FIXED_NOW_ts - 120_000


def test_fetch_candles_binance_open_candle_is_not_closed(patch_datetime_now):
    open_ms = FIXED_NOW_ts - 30000
    close_ms = FIXED_NOW_ts + 30000
    client = MagicMock()
    client.get_historical_klines.return_value = [
        [open_ms, "1", "1", "1", "1", "1", close_ms, 0, 0, 0, 0, 0]
    ]

    result = fd.fetch_candles_binance(client)
    assert result["candles"][0]["is_closed"] is False


def test_fetch_candles_binance_empty_response(patch_datetime_now):
    client = MagicMock()
    client.get_historical_klines.return_value = []
    result = fd.fetch_candles_binance(client)
    assert result["candles"] == []


def test_fetch_candles_coinbase_maps_fields_and_defaults(patch_datetime_now, monkeypatch):
    mock_response = MagicMock()
    open_s = FIXED_NOW_ts / 1000
    mock_response.json.return_value = [[open_s, 1.0, 2.0, 1.1, 1.9, 5.0]]
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr(fd.requests, "get", mock_get)

    result = fd.fetch_candles_coinbase(symbol="BTC-USD", interval="60")

    assert result["exchange"] == "Coinbase"
    assert result["interval"] == "60s"
    candle = result["candles"][0]
    _assert_candle_keys(candle, closed_key="closed")
    assert candle["low"] == 1.0
    assert candle["high"] == 2.0
    assert candle["open"] == 1.1
    assert candle["close"] == 1.9
    assert candle["volume"] == 5.0
    # Current logic: True while candle window still overlaps "now"
    assert candle["closed"] is False

    params = mock_get.call_args.kwargs["params"]
    assert params["granularity"] == "60"
    assert int(params["end"]) == FIXED_NOW_ts / 1000
    assert int(params["start"]) == FIXED_NOW_ts / 1000 - 120


def test_fetch_candles_okx_maps_fields(patch_datetime_now, monkeypatch):
    open_ms = FIXED_NOW_ts - 60000
    mock_api = MagicMock()
    mock_api.get_candlesticks.return_value = {
        "data": [[str(open_ms), "1", "2", "0.5", "1.5", "10", "0", "0", "1"]]
    }
    monkeypatch.setattr(fd.MD, "MarketAPI", MagicMock(return_value=mock_api))

    result = fd.fetch_candles_okx(symbol="BTC-USDT", interval="1m")

    assert result["exchange"] == "OKX"
    assert result["interval"] == "1m"
    candle = result["candles"][0]
    _assert_candle_keys(candle)
    assert candle["open"] == 1.0
    assert candle["high"] == 2.0
    assert candle["low"] == 0.5
    assert candle["close"] == 1.5
    assert candle["volume"] == 10.0
    assert candle["is_closed"] == 1

    kwargs = mock_api.get_candlesticks.call_args.kwargs
    assert kwargs["instId"] == "BTC-USDT"
    assert kwargs["bar"] == "1m"
    assert kwargs["after"] == str(FIXED_NOW_ts)
    assert kwargs["before"] == str(FIXED_NOW_ts - 120000)


def test_fetch_candles_bybit_maps_fields(patch_datetime_now):
    open_ms = FIXED_NOW_ts - 60000
    session = MagicMock()
    session.get_kline.return_value = {
        "result": {
            "list": [[str(open_ms), "1", "2", "0.5", "1.5", "10", "0"]]
        }
    }

    result = fd.fetch_candles_bybit(session, symbol="BTCUSD", interval=60)

    assert result["exchange"] == "ByBit"
    assert result["interval"] == "60s"
    candle = result["candles"][0]
    _assert_candle_keys(candle)
    assert candle["open"] == 1.0
    assert candle["high"] == 2.0
    assert candle["low"] == 0.5
    assert candle["close"] == 1.5
    assert candle["volume"] == 10.0
    assert candle["is_closed"] is False

    kwargs = session.get_kline.call_args.kwargs
    assert kwargs["category"] == "spot"
    assert kwargs["symbol"] == "BTCUSD"
    assert kwargs["start"] == FIXED_NOW_ts - 120000
    assert kwargs["end"] == FIXED_NOW_ts


def test_fetch_candles_bitget_maps_fields(patch_datetime_now, monkeypatch):
    open_ms = FIXED_NOW_ts - 60000
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": "00000",
        "data": [[str(open_ms), "1", "2", "0.5", "1.5", "8", "10"]],
    }
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr(fd.requests, "get", mock_get)

    result = fd.fetch_candles_bitget(symbol="BTCUSDT", interval="1min")

    assert result["exchange"] == "BitGet"
    assert result["interval"] == "1min"
    candle = result["candles"][0]
    _assert_candle_keys(candle)
    assert candle["open"] == 1.0
    assert candle["high"] == 2.0
    assert candle["low"] == 0.5
    assert candle["close"] == 1.5
    assert candle["volume"] == 10.0
    assert candle["is_closed"] is False

    params = mock_get.call_args.kwargs["params"]
    assert params["symbol"] == "BTCUSDT"
    assert params["granularity"] == "1min"
    assert params["startTime"] == str(FIXED_NOW_ts - 120_000)
    assert params["endTime"] == str(FIXED_NOW_ts)


# --- Order books -------------------------------------------------------------


def test_fetch_spot_order_book_binance(patch_datetime_now):
    client = MagicMock()
    client.get_order_book.return_value = {
        "bids": [["1", "2"]],
        "asks": [["3", "4"]],
    }

    result = fd.fetch_spot_order_book_binance(client, symbol="BTCUSDT", limit=50)

    _assert_order_book_meta(result, exchange="Binance", symbol="BTCUSDT", depth=50)
    assert result["order_book"]["bids"] == [["1", "2"]]
    client.get_order_book.assert_called_once_with(symbol="BTCUSDT", limit=50)


def test_fetch_spot_order_book_coinbase(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "pricebook": {
            "product_id": "BTC-USD",
            "bids": [
                {"price": str(i), "size": "1", "order_id": "x"} for i in range(5)
            ],
            "asks": [
                {"price": str(i), "size": "1", "order_id": "y"} for i in range(5)
            ],
            "time": "2024-01-01T12:00:05.000Z",
        }
    }
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr(fd.requests, "get", mock_get)

    result = fd.fetch_spot_order_book_coinbase(symbol="BTC-USD", limit=2)

    _assert_order_book_meta(result, exchange="Coinbase", symbol="BTC-USD", depth=2)
    assert result["order_book"]["bids"] == [["0", "1"], ["1", "1"]]
    assert result["order_book"]["asks"] == [["0", "1"], ["1", "1"]]
    assert result["sampled_at"] == datetime(2024, 1, 1, 13, 0, 5, tzinfo=cfg.TIMEZONE)
    mock_get.assert_called_once_with(
        "https://api.coinbase.com/api/v3/brokerage/market/product_book",
        params={"product_id": "BTC-USD", "limit": 2},
        timeout=cfg.HTTP_TIMEOUT,
    )


def test_fetch_spot_order_book_okx(monkeypatch):
    mock_api = MagicMock()
    mock_api.get_orderbook.return_value = {
        "data": [{
            "asks": [["3", "1", "0", "1"]],
            "bids": [["2", "1", "0", "1"]],
            "ts": str(FIXED_NOW_ts),
        }]
    }
    monkeypatch.setattr(fd.MD, "MarketAPI", MagicMock(return_value=mock_api))

    result = fd.fetch_spot_order_book_okx(symbol="BTC-USDT", limit=100)

    _assert_order_book_meta(result, exchange="OKX", symbol="BTC-USDT", depth=100)
    assert result["order_book"]["bids"][0][0] == "2"
    mock_api.get_orderbook.assert_called_once_with(instId="BTC-USDT", sz=100)


def test_fetch_spot_order_book_bybit():
    session = MagicMock()
    session.get_orderbook.return_value = {
        "result": {
            "b": [["2", "1"]],
            "a": [["3", "1"]],
            "ts": str(FIXED_NOW_ts),
        }
    }

    result = fd.fetch_spot_order_book_bybit(session, symbol="BTCUSD", limit=50)

    _assert_order_book_meta(result, exchange="Bybit", symbol="BTCUSD", depth=50)
    assert result["order_book"] == {"bids": [["2", "1"]], "asks": [["3", "1"]]}
    session.get_orderbook.assert_called_once_with(
        category="spot", symbol="BTCUSD", limit=50
    )


def test_fetch_spot_order_book_bitget(monkeypatch):
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "code": "00000",
        "data": {
            "asks": [["3", "1"]],
            "bids": [["2", "1"]],
            "ts": str(FIXED_NOW_ts),
        },
    }
    mock_get = MagicMock(return_value=mock_response)
    monkeypatch.setattr(fd.requests, "get", mock_get)

    result = fd.fetch_spot_order_book_bitget(symbol="BTCUSDT", limit=100)

    _assert_order_book_meta(result, exchange="Bitget", symbol="BTCUSDT", depth=100)
    assert result["order_book"]["asks"] == [["3", "1"]]
    assert mock_get.call_args.kwargs["params"] == {
        "symbol": "BTCUSDT",
        "type": "step0",
        "limit": "100",
    }


# --- fetch_data --------------------------------------------------------------


def test_fetch_data_runs_candles_and_orderbook(monkeypatch):
    candles = {"exchange": "Coinbase", "candles": []}
    orderbook = {"exchange": "Coinbase", "order_book": {}}
    candles_fn = MagicMock(return_value=candles)
    orderbook_fn = MagicMock(return_value=orderbook)
    monkeypatch.setitem(fd.ADAPTERS, "Coinbase", {
        "make_client": None,
        "candles": candles_fn,
        "orderbook": orderbook_fn,
    })

    result = fd.fetch_data("Coinbase", "BTCUSD", "1m", 1, 2, 100)

    assert result == {
        "exchange": "Coinbase",
        "candles": candles,
        "orderbook": orderbook,
    }
    candles_fn.assert_called_once_with(symbol="BTC-USD", interval="60", start=1, end=2)
    orderbook_fn.assert_called_once_with(symbol="BTC-USD", limit=100)


def test_fetch_data_passes_client_when_make_client_set(monkeypatch):
    client = object()
    candles_fn = MagicMock(return_value={"candles": []})
    orderbook_fn = MagicMock(return_value={"order_book": {}})
    monkeypatch.setitem(fd.ADAPTERS, "Binance", {
        "make_client": lambda: client,
        "candles": candles_fn,
        "orderbook": orderbook_fn,
    })

    fd.fetch_data("Binance", "BTCUSD", "1m", 1, 2, 50)

    candles_fn.assert_called_once_with(
        client, symbol="BTCUSDT", interval="1m", start=1, end=2
    )
    orderbook_fn.assert_called_once_with(client, symbol="BTCUSDT", limit=50)


# --- persistence -------------------------------------------------------------


def _sample_candle(open_time: datetime, close: float, **extra) -> dict:
    row = {
        "open_time": open_time,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "is_closed": True,
    }
    row.update(extra)
    return row


def _sample_orderbook(sampled_at: datetime, bids=None, asks=None) -> dict:
    return {
        "exchange": "Binance",
        "symbol": "BTCUSDT",
        "sampled_at": sampled_at,
        "minute_bucket": sampled_at.replace(second=0, microsecond=0),
        "order_book": {
            "bids": bids if bids is not None else [["100", "1"]],
            "asks": asks if asks is not None else [["101", "2"]],
        },
        "depth": 100,
    }


def test_save_candles_creates_single_file_and_upserts_by_open_time(tmp_path):
    t0 = datetime(2024, 1, 1, 12, 0, tzinfo=cfg.TIMEZONE)
    t1 = datetime(2024, 1, 1, 12, 1, tzinfo=cfg.TIMEZONE)

    path = fd.save_candles(
        "Binance",
        "BTCUSD",
        "1m",
        [_sample_candle(t0, 1.0), _sample_candle(t1, 2.0)],
        data_dir=tmp_path,
    )

    assert path == tmp_path / "Binance" / "BTCUSD_1m.parquet"
    first = pd.read_parquet(path)
    assert list(first["close"]) == [1.0, 2.0]

    t2 = datetime(2024, 1, 1, 12, 2, tzinfo=cfg.TIMEZONE)
    fd.save_candles(
        "Binance",
        "BTCUSD",
        "1m",
        [_sample_candle(t1, 2.5), _sample_candle(t2, 3.0)],
        data_dir=tmp_path,
    )

    saved = pd.read_parquet(path)
    assert list(saved["open_time"]) == [t0, t1, t2]
    assert list(saved["close"]) == [1.0, 2.5, 3.0]


def test_save_candles_skips_empty_batch(tmp_path):
    assert fd.save_candles("Binance", "BTCUSD", "1m", [], data_dir=tmp_path) is None
    assert not list(tmp_path.rglob("*.parquet"))


def _nested_list(value):
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [list(level) if not isinstance(level, list) else level for level in value]


def test_save_orderbook_uses_minute_filename_and_keeps_raw_sides(tmp_path):
    sampled_at = datetime(2024, 1, 1, 12, 3, 45, tzinfo=cfg.TIMEZONE)
    bids = [["100", "1"], ["99", "4"]]
    asks = [["101", "2"]]
    path = fd.save_orderbook(
        "Binance",
        "BTCUSD",
        _sample_orderbook(sampled_at, bids=bids, asks=asks),
        data_dir=tmp_path,
    )

    assert path == tmp_path / "Binance" / "BTCUSD_2024-01-01_12-03.parquet"
    saved = pd.read_parquet(path)
    assert len(saved) == 1
    assert _nested_list(saved.iloc[0]["bids"]) == bids
    assert _nested_list(saved.iloc[0]["asks"]) == asks
    assert "side" not in saved.columns
    assert "level" not in saved.columns


def test_save_orderbook_appends_second_snapshot_in_same_minute(tmp_path):
    t1 = datetime(2024, 1, 1, 12, 3, 10, tzinfo=cfg.TIMEZONE)
    t2 = datetime(2024, 1, 1, 12, 3, 40, tzinfo=cfg.TIMEZONE)
    fd.save_orderbook("Binance", "BTCUSD", _sample_orderbook(t1), data_dir=tmp_path)
    path = fd.save_orderbook(
        "Binance",
        "BTCUSD",
        _sample_orderbook(t2, bids=[["99", "3"]], asks=[["102", "4"]]),
        data_dir=tmp_path,
    )

    saved = pd.read_parquet(path)
    assert saved["sampled_at"].nunique() == 2
    later = saved[saved["sampled_at"] == t2].iloc[0]
    assert _nested_list(later["bids"]) == [["99", "3"]]
    assert _nested_list(later["asks"]) == [["102", "4"]]






