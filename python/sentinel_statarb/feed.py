from __future__ import annotations

import argparse
import asyncio
import math
import struct
import time
from dataclasses import dataclass

import zmq.asyncio


@dataclass
class BestQuote:
    bid: float
    ask: float
    receipt_ns: int


class CryptofeedBridge:
    """Bridge normalized Cryptofeed L2 callbacks into Sentinel TickMessage frames."""

    def __init__(self, endpoint: str, symbol_a: str = "BTC-USD", symbol_b: str = "ETH-USD"):
        self.symbol_a = symbol_a
        self.symbol_b = symbol_b
        self.books: dict[str, BestQuote] = {}
        self.seq = 0
        self.invalid_books = 0
        self.ctx = zmq.asyncio.Context.instance()
        self.socket = self.ctx.socket(zmq.PUSH)
        self.socket.connect(endpoint)

    async def close(self) -> None:
        self.socket.close(0)

    async def on_book(self, book, receipt_timestamp: float) -> None:
        if not len(book.book.bids) or not len(book.book.asks):
            return
        bid, _ = book.book.bids.index(0)
        ask, _ = book.book.asks.index(0)
        bid = float(bid)
        ask = float(ask)
        if not (
            math.isfinite(bid)
            and math.isfinite(ask)
            and bid > 0.0
            and ask >= bid
        ):
            self.invalid_books += 1
            return
        self.books[book.symbol] = BestQuote(
            bid, ask, int(receipt_timestamp * 1e9)
        )
        if self.symbol_a not in self.books or self.symbol_b not in self.books:
            return

        a = self.books[self.symbol_a]
        b = self.books[self.symbol_b]
        self.seq += 1

        payload = struct.pack(
            "<BQQddddd",
            1,
            self.seq,
            time.monotonic_ns(),
            a.bid,
            a.ask,
            b.bid,
            b.ask,
            0.001,
        )
        await self.socket.send(payload)


async def run_live(
    endpoint: str,
    exchange: str = "COINBASE",
    symbol_a: str = "BTC-USD",
    symbol_b: str = "ETH-USD",
) -> None:
    from cryptofeed import FeedHandler
    from cryptofeed.defines import L2_BOOK
    from cryptofeed.exchanges import EXCHANGE_MAP

    try:
        exchange_cls = EXCHANGE_MAP[exchange.upper()]
    except KeyError as exc:
        raise SystemExit(f"Unsupported exchange: {exchange}") from exc

    bridge = CryptofeedBridge(endpoint, symbol_a, symbol_b)
    fh = FeedHandler(on_feed_error="remove_feed")
    fh.add_feed(
        exchange_cls(
            symbols=[symbol_a, symbol_b],
            channels=[L2_BOOK],
            callbacks={L2_BOOK: bridge.on_book},
        )
    )
    try:
        await fh.run_async()
    finally:
        await bridge.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Bridge a public Cryptofeed L2 feed into Sentinel"
    )
    parser.add_argument("--endpoint", default="ipc:///tmp/sentinel_exec_in.ipc")
    parser.add_argument("--exchange", default="COINBASE")
    parser.add_argument("--symbol-a", default="BTC-USD")
    parser.add_argument("--symbol-b", default="ETH-USD")
    args = parser.parse_args()
    asyncio.run(
        run_live(args.endpoint, args.exchange, args.symbol_a, args.symbol_b)
    )


if __name__ == "__main__":
    main()
