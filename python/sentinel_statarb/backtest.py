from __future__ import annotations

from dataclasses import dataclass
from typing import List

import numpy as np

from .strategy import PairStrategy, Tick


@dataclass
class BacktestResult:
    label: str
    seed: int
    ticks: int
    trades_entered: int
    exits: int
    stop_exits: int
    pnl: float
    max_drawdown: float
    flash_crash_loss: float


def generate_path(
    seed: int = 7,
    n: int = 50_000,
    crash_at: int | None = None,
) -> List[Tick]:
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 0.0007, n)
    a_noise = rng.normal(0, 0.0009, n)
    b_noise = rng.normal(0, 0.0009, n)
    log_a = np.empty(n)
    log_b = np.empty(n)
    log_a[0], log_b[0] = np.log(100.0), np.log(100.0)

    for i in range(1, n):
        log_a[i] = log_a[i - 1] + common[i] + a_noise[i]
        log_b[i] = log_b[i - 1] + common[i] + b_noise[i]

    if crash_at is not None:
        pre0 = max(0, crash_at - 30)
        log_a[pre0:crash_at] += np.linspace(0.0, 0.006, crash_at - pre0)
        end = min(n, crash_at + 20)
        log_a[crash_at:end] += np.linspace(0.006, 0.035, end - crash_at)
        recover_end = min(n, end + 30)
        log_a[end:recover_end] += np.linspace(0.035, 0.0, recover_end - end)

    prices_a, prices_b = np.exp(log_a), np.exp(log_b)
    vol = np.full(n, 0.001)
    if crash_at is not None:
        vol[max(0, crash_at - 5):min(n, crash_at + 45)] = 0.010

    return [
        Tick(
            i * 1_000_000,
            p_a - 0.0025,
            p_a + 0.0025,
            p_b - 0.0025,
            p_b + 0.0025,
            float(vol[i]),
        )
        for i, (p_a, p_b) in enumerate(zip(prices_a, prices_b))
    ]


def run(
    seed: int = 7,
    n: int = 50_000,
    crash_at: int = 25_000,
    dynamic: bool = True,
) -> BacktestResult:
    ticks = generate_path(seed, n, crash_at)
    strategy = PairStrategy()

    if not dynamic:
        strategy.debouncer.base = 1
        strategy.debouncer.max_confirmations = 1
        strategy.debouncer.reference_vol = 1.0

    cash = 0.0
    position = 0
    entry = 0.0
    equity = []
    crash_equity = 0.0

    for idx, tick in enumerate(ticks):
        strategy.update(tick)
        mid_a = 0.5 * (tick.bid_a + tick.ask_a)
        mid_b = 0.5 * (tick.bid_b + tick.ask_b)
        spread = mid_a - strategy.beta.beta * mid_b

        if position == 0 and strategy.position != 0:
            position = strategy.position
            entry = spread
        elif position != 0 and strategy.position == 0:
            cash += -position * (spread - entry)
            position = 0

        mtm = cash - position * (spread - entry if position else 0.0)
        equity.append(mtm)

        if idx == crash_at:
            crash_equity = mtm

    if position:
        cash += -position * (spread - entry)

    eq = np.asarray(equity)
    peak = np.maximum.accumulate(eq)
    drawdown = float(np.min(eq - peak))

    return BacktestResult(
        "dynamic" if dynamic else "baseline",
        seed,
        n,
        strategy.entries,
        strategy.exits,
        strategy.stop_exits,
        float(cash),
        drawdown,
        float(crash_equity),
    )
