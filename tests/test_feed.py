import asyncio
import struct
from pathlib import Path
from unittest.mock import AsyncMock

import sys

sys.path.insert(0, str(Path(__file__).parents[1] / "python"))

from sentinel_statarb.feed import CryptofeedBridge


class _Levels:
    def __init__(self, bid_or_ask):
        self.value = bid_or_ask

    def __len__(self):
        return 1

    def index(self, _):
        return self.value, 2.5


class _Book:
    def __init__(self, symbol: str, bid: float, ask: float):
        self.symbol = symbol
        self.book = self
        self.bids = _Levels(bid)
        self.asks = _Levels(ask)


class _EmptyBook:
    symbol = "BTC-USD"

    class _Book:
        bids = ()
        asks = ()

    book = _Book()


def test_bridge_waits_for_both_symbols_before_emitting():
    async def scenario():
        bridge = CryptofeedBridge(
            "inproc://sentinel-test-feed",
            symbol_a="BTC-USD",
            symbol_b="ETH-USD",
        )
        bridge.socket.send = AsyncMock()

        await bridge.on_book(_Book("BTC-USD", 100.0, 100.1), 123.456)
        bridge.socket.send.assert_not_awaited()

        await bridge.on_book(_Book("ETH-USD", 200.0, 200.2), 123.789)
        assert bridge.socket.send.await_count == 1

        payload = bridge.socket.send.await_args.args[0]
        type_, seq, _, bid_a, ask_a, bid_b, ask_b, vol = struct.unpack(
            "<BQQddddd", payload
        )
        assert type_ == 1
        assert seq == 1
        assert (bid_a, ask_a, bid_b, ask_b) == (100.0, 100.1, 200.0, 200.2)
        assert vol == 0.001

        await bridge.close()

    asyncio.run(scenario())


def test_bridge_ignores_empty_books():
    async def scenario():
        bridge = CryptofeedBridge(
            "inproc://sentinel-test-empty-feed",
            symbol_a="BTC-USD",
            symbol_b="ETH-USD",
        )
        bridge.socket.send = AsyncMock()

        await bridge.on_book(_EmptyBook(), 123.456)
        bridge.socket.send.assert_not_awaited()
        assert bridge.books == {}

        await bridge.close()

    asyncio.run(scenario())
