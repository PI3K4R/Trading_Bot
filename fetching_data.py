from concurrent.futures import ThreadPoolExecutor, as_completed, wait
from binance import Client as Client_binance
import pybit.unified_trading
from okx import MarketData as MD
import requests
from datetime import datetime
import config as cfg
import pandas as pd
from pathlib import Path


def _bitget_payload(response: requests.Response) -> dict:
    payload = response.json()
    if str(payload.get("code")) not in {"00000", "0"}:
        raise RuntimeError(payload.get("msg") or payload)
    return payload


def fetch_candles_binance(client: Client_binance, symbol: str = "BTCUSDT", interval: str = "1m", start: float = None, end: float = None) -> dict:

    now = int(datetime.now().timestamp())

    if end is None:
        end = now
    if start is None:
        start = end - 120

    response = client.get_historical_klines(
        symbol=symbol,
        interval=interval,
        start_str=str(int(start) * 1000),
        end_str=str(int(end) * 1000),
    )

    candles = []

    for row in response:
        open_time = int(row[0])
        close_time = int(row[6])
        is_closed = close_time/1000 < now
        candles.append({
            "open_time": datetime.fromtimestamp(open_time / 1000, tz=cfg.TIMEZONE).replace(microsecond=0),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "close_time": datetime.fromtimestamp(close_time / 1000, tz=cfg.TIMEZONE).replace(microsecond=0),
            "is_closed": is_closed
        })
    return {
        "exchange": "Binance",
        "interval": interval,
        "endtime": candles[-1]["close_time"] if candles else None,
        "candles": candles,
    }


def fetch_candles_coinbase(symbol: str = "BTC-USD", interval: str = "60", start: float = None, end: float = None) -> dict:
    url = f"https://api.exchange.coinbase.com/products/{symbol}/candles"

    now = int(datetime.now().timestamp())

    if end is None:
        end = now
    if start is None:
        start = end - 120

    response = requests.get(url, params={"granularity": interval, "start": str(start), "end": str(end)}, timeout=cfg.HTTP_TIMEOUT)
    rows = response.json()
    granularity = int(interval)

    candles = []

    for row in rows:
        open_time = int(row[0])
        is_closed = open_time + granularity < now
        candles.append({
            "open_time": datetime.fromtimestamp(open_time, tz=cfg.TIMEZONE),
            "low": float(row[1]),
            "high": float(row[2]),
            "open": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "closed": is_closed
        })
    return {"exchange": "Coinbase",
            "interval": interval + "s",
            "candles": candles}


def fetch_candles_okx(symbol: str = "BTC-USDT", interval: str = "1m", start: int = None, end: int = None) -> dict:
    flag = "1"

    now = int(datetime.now().timestamp())

    if end is None:
        end = now
    if start is None:
        start = end - 120

    market_data_api = MD.MarketAPI(flag=flag)
    market_data_api.timeout = cfg.HTTP_TIMEOUT
    response = market_data_api.get_candlesticks(instId=symbol, bar=interval, after=str(end*1000), before=str(start*1000))

    candles = []

    for row in response["data"]:
        open_time = int(row[0])
        candles.append({
            "open_time": datetime.fromtimestamp(open_time / 1000, tz=cfg.TIMEZONE),
            "low": float(row[3]),
            "high": float(row[2]),
            "open": float(row[1]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "is_closed": int(row[8])
        })
    return {"exchange": "OKX",
            "interval": interval,
            "candles": candles}


def fetch_candles_bybit(session: pybit.unified_trading.HTTP, symbol: str = "BTCUSD", interval: int = 60, start: float = None, end: float = None) -> dict:
    now = int(datetime.now().timestamp())

    if end is None:
        end = now
    if start is None:
        start = end - 120

    response = session.get_kline(category="spot", symbol=symbol, interval=interval, start=start*1000, end=end*1000)

    candles_data = response["result"]
    candles = []

    for row in candles_data["list"]:
        open_time = int(row[0])
        is_closed = open_time + interval * 1000 < now * 1000
        candles.append({
            "open_time": datetime.fromtimestamp(open_time / 1000, tz=cfg.TIMEZONE),
            "low": float(row[3]),
            "high": float(row[2]),
            "open": float(row[1]),
            "close": float(row[4]),
            "volume": float(row[5]),
            "is_closed": is_closed
        })
    return {"exchange": "ByBit",
            "interval": str(interval) + "s",
            "candles": candles}


def fetch_candles_bitget(symbol: str = "BTCUSDT", interval: str = "1min", start: float = None, end: float = None) -> dict:
    now = int(datetime.now().timestamp())
    url = "https://api.bitget.com/api/v2/spot/market/candles"
    intervals = {"1min": 60}

    if end is None:
        end = now
    if start is None:
        start = end - 120

    response = requests.get(
        url,
        params={
            "symbol": symbol,
            "granularity": interval,
            "startTime": str(int(start) * 1000),
            "endTime": str(int(end) * 1000),
        },
        timeout=cfg.HTTP_TIMEOUT,
    )
    rows = _bitget_payload(response).get("data") or []

    candles = []
    for row in rows:
        open_time = int(row[0])
        is_closed = open_time + intervals[interval] * 1000 < now * 1000
        candles.append({
            "open_time": datetime.fromtimestamp(open_time / 1000, tz=cfg.TIMEZONE),
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[6] if len(row) > 6 else row[5]),
            "is_closed": is_closed,
        })
    return {"exchange": "BitGet",
            "interval": interval,
            "candles": candles}

def fetch_spot_order_book_binance(client: Client_binance, symbol: str = "BTCUSDT", limit: int = 100) -> dict:
    order_book = client.get_order_book(symbol=symbol, limit=limit)
    sampled_at = datetime.now().timestamp()

    return {
        "exchange": "Binance",
        "symbol": symbol,
        "sampled_at": datetime.fromtimestamp(sampled_at, tz=cfg.TIMEZONE),
        "minute_bucket": datetime.fromtimestamp(sampled_at, tz=cfg.TIMEZONE).replace(second=0, microsecond=0),
        "order_book": order_book,
        "depth": limit
    }

def _price_size_levels(levels: list, limit: int) -> list:
    """Keep the top `limit` book rows as [price, size], matching Binance/Bybit/Bitget."""
    rows = []
    for entry in levels[:limit]:
        if isinstance(entry, dict):
            rows.append([str(entry["price"]), str(entry["size"])])
        else:
            rows.append([str(entry[0]), str(entry[1])])
    return rows


def fetch_spot_order_book_coinbase(symbol: str = "BTC-USD", limit: int = 100) -> dict:
    url = "https://api.coinbase.com/api/v3/brokerage/market/product_book"
    response = requests.get(
        url,
        params={"product_id": symbol, "limit": limit},
        timeout=cfg.HTTP_TIMEOUT,
    )
    response.raise_for_status()
    book = response.json()["pricebook"]
    sampled_at = datetime.fromisoformat(book["time"].replace("Z", "+00:00")).astimezone(cfg.TIMEZONE)
    order_book = {
        "bids": _price_size_levels(book.get("bids") or [], limit),
        "asks": _price_size_levels(book.get("asks") or [], limit),
    }

    return {
        "exchange": "Coinbase",
        "symbol": symbol,
        "sampled_at": sampled_at,
        "minute_bucket": sampled_at.replace(second=0, microsecond=0),
        "order_book": order_book,
        "depth": limit
    }

def fetch_spot_order_book_okx(symbol: str = "BTC-USDT", limit: int = 100) -> dict:
    flag = "1"
    market_data_api = MD.MarketAPI(flag=flag)
    market_data_api.timeout = cfg.HTTP_TIMEOUT
    order_book = market_data_api.get_orderbook(instId=symbol, sz=limit)
    book = order_book["data"][0]
    sampled_at = datetime.fromtimestamp(int(book["ts"]) / 1000, tz=cfg.TIMEZONE)

    return {
        "exchange": "OKX",
        "symbol": symbol,
        "sampled_at": sampled_at,
        "minute_bucket": sampled_at.replace(second=0, microsecond=0),
        "order_book": book,
        "depth": limit
    }


def fetch_spot_order_book_bybit(session: pybit.unified_trading.HTTP, symbol: str = "BTCUSD", limit: int = 100) -> dict:
    response = session.get_orderbook(
        category="spot",
        symbol=symbol,
        limit=limit
    )
    book = response["result"]
    sampled_at = datetime.fromtimestamp(int(book["ts"]) / 1000, tz=cfg.TIMEZONE)
    order_book = {"bids": book["b"], "asks": book["a"]}

    return {
        "exchange": "Bybit",
        "symbol": symbol,
        "sampled_at": sampled_at,
        "minute_bucket": sampled_at.replace(second=0, microsecond=0),
        "order_book": order_book,
        "depth": limit
    }


def fetch_spot_order_book_bitget(symbol: str = "BTCUSDT", limit: int = 100) -> dict:
    url = "https://api.bitget.com/api/v2/spot/market/orderbook"
    response = requests.get(
        url,
        params={"symbol": symbol, "type": "step0", "limit": str(limit)},
        timeout=cfg.HTTP_TIMEOUT,
    )
    book = _bitget_payload(response)["data"]
    sampled_at = datetime.fromtimestamp(int(book["ts"]) / 1000, tz=cfg.TIMEZONE)

    return {
        "exchange": "Bitget",
        "symbol": symbol,
        "sampled_at": sampled_at,
        "minute_bucket": sampled_at.replace(second=0, microsecond=0),
        "order_book": book,
        "depth": limit
    }


ADAPTERS = {
    "Binance": {
        "make_client": lambda: Client_binance(ping=False, requests_params={"timeout": cfg.HTTP_TIMEOUT}),
        "candles": fetch_candles_binance,
        "orderbook": fetch_spot_order_book_binance,
    },
    "Coinbase": {
        "make_client": None,
        "candles": fetch_candles_coinbase,
        "orderbook": fetch_spot_order_book_coinbase,
    },
    "OKX": {
        "make_client": None,
        "candles": fetch_candles_okx,
        "orderbook": fetch_spot_order_book_okx,
    },
    "Bybit": {
        "make_client": lambda: pybit.unified_trading.HTTP(testnet=False, timeout=cfg.HTTP_TIMEOUT),
        "candles": fetch_candles_bybit,
        "orderbook": fetch_spot_order_book_bybit,
    },
    "Bitget": {
        "make_client": None,
        "candles": fetch_candles_bitget,
        "orderbook": fetch_spot_order_book_bitget,
    },
}


def _adapter_call(fn, make_client, *, attempts=1, **kwargs):
    last_exc = None
    for attempt in range(1, attempts + 1):
        try:
            client = make_client() if make_client else None
            if client is None:
                return fn(**kwargs)
            return fn(client, **kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt == attempts:
                raise
    raise last_exc


def fetch_data(exchange, symbol, interval, start, end, limit):
    native_symbol = cfg.SYMBOLS[symbol][exchange]
    native_interval = cfg.INTERVALS[interval][exchange]
    adapter = ADAPTERS[exchange]
    make_client = adapter["make_client"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        candles_fut = pool.submit(
            lambda: _adapter_call(
            adapter["candles"],
            make_client,
            attempts=1,
            symbol=native_symbol,
            interval=native_interval,
            start=start,
            end=end,
        ))
        orderbook_fut = pool.submit(
            lambda: _adapter_call(
            adapter["orderbook"],
            make_client,
            attempts=cfg.ORDERBOOK_ATTEMPTS,
            symbol=native_symbol,
            limit=limit,
        ))
        wait((candles_fut, orderbook_fut))

        try:
            candles = candles_fut.result()
        except Exception as exc:
            print(f"{exchange} candles: failed ({exc})")
            candles = {"candles": []}
        try:
            orderbook = orderbook_fut.result()
        except Exception as exc:
            print(f"{exchange} orderbook: failed ({exc})")
            orderbook = None

    return {
        "exchange": exchange,
        "candles": candles,
        "orderbook": orderbook,
    }


def _candles_file_path(exchange: str, symbol: str, interval: str, data_dir=None) -> Path:
    root = Path(data_dir or cfg.CANDLES_DATA_DIR)
    return root / exchange / f"{symbol}_{interval}.parquet"


def _orderbook_file_path(exchange: str, symbol: str, minute_bucket: datetime, data_dir=None) -> Path:
    stamp = minute_bucket.strftime("%Y-%m-%d_%H-%M")
    root = Path(data_dir or cfg.ORDERBOOK_DATA_DIR)
    return root / exchange / f"{symbol}_{stamp}.parquet"


def save_candles(exchange: str, symbol: str, interval: str, candles: list, *, data_dir=None) -> Path | None:
    """Upsert candles into one parquet per exchange/symbol/interval.

    Existing rows with the same open_time are overwritten by the newest batch.
    """
    if not candles:
        return None

    path = _candles_file_path(exchange, symbol, interval, data_dir=data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = pd.DataFrame(candles)
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, incoming], ignore_index=True)
    else:
        combined = incoming
    combined = combined.drop_duplicates(subset=["open_time"], keep="last")
    combined = combined.sort_values("open_time").reset_index(drop=True)
    combined.to_parquet(path, index=False)
    return path


def _orderbook_snapshot_row(orderbook: dict, *, symbol: str) -> pd.DataFrame:
    book = orderbook.get("order_book") or {}
    return pd.DataFrame([{
        "exchange": orderbook["exchange"],
        "symbol": symbol,
        "sampled_at": orderbook["sampled_at"],
        "minute_bucket": orderbook["minute_bucket"],
        "bids": list(book.get("bids") or []),
        "asks": list(book.get("asks") or []),
        "depth": orderbook.get("depth"),
    }])


def save_orderbook(exchange: str, symbol: str, orderbook: dict, *, data_dir=None) -> Path:
    """Write one parquet row per snapshot. Extra snapshots in the same minute are appended."""
    path = _orderbook_file_path(exchange, symbol, orderbook["minute_bucket"], data_dir=data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    incoming = _orderbook_snapshot_row(orderbook, symbol=symbol)
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, incoming], ignore_index=True)
        combined = combined.drop_duplicates(subset=["sampled_at"], keep="last")
    else:
        combined = incoming
    combined.to_parquet(path, index=False)
    return path


if __name__ == "__main__":
    now = int(datetime.now(tz=cfg.TIMEZONE).timestamp())
    start = now - 600
    end = now

    with ThreadPoolExecutor(max_workers=len(cfg.EXCHANGES)) as pool:
        futures = {
            pool.submit(
                fetch_data,
                exchange,
                cfg.SYMBOL,
                cfg.INTERVAL,
                start,
                end,
                cfg.ORDER_BOOK_DEPTH,
            ): exchange
            for exchange in cfg.EXCHANGES
        }
        for fut in as_completed(futures):
            exchange = futures[fut]
            try:
                result = fut.result()
                save_candles(exchange, cfg.SYMBOL, cfg.INTERVAL, result["candles"]["candles"])
                if result["orderbook"] is not None:
                    save_orderbook(exchange, cfg.SYMBOL, result["orderbook"])
                print(f"{exchange}: ok")
            except Exception as exc:
                print(f"{exchange}: failed ({exc})")

    