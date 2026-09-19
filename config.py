"""Canonical symbols/intervals and per-exchange API mappings."""

from zoneinfo import ZoneInfo

EXCHANGES = ("Binance", "Coinbase", "OKX", "Bybit", "Bitget")
CANDLES_DATA_DIR = "raw_exchanges_data/candles"
ORDERBOOK_DATA_DIR = "raw_exchanges_data/orderbooks"

# Canonical symbol -> exchange-native ticker
SYMBOLS = {
    "BTCUSD": {
        "Binance": "BTCUSDT",
        "Coinbase": "BTC-USD",
        "OKX": "BTC-USDT",
        "Bybit": "BTCUSDT",
        "Bitget": "BTCUSDT",
    },
    "ETHUSD": {
        "Binance": "ETHUSDT",
        "Coinbase": "ETH-USD",
        "OKX": "ETH-USDT",
        "Bybit": "ETHUSDT",
        "Bitget": "ETHUSDT",
    },
}

# Canonical interval -> exchange-native period
INTERVALS = {
    "1m": {
        "Binance": "1m",
        "Coinbase": "60",
        "OKX": "1m",
        "Bybit": 60,
        "Bitget": "1min",
    },
}

SYMBOL = "BTCUSD"
INTERVAL = "1m"
# Top N L2 price levels per side. 100 is the largest value all five REST APIs accept.
ORDER_BOOK_DEPTH = 10000
TIMEZONE = ZoneInfo("Europe/Warsaw")
HTTP_TIMEOUT = 10
ORDERBOOK_ATTEMPTS = 3
