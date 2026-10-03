from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Tick:
    ts_ns: int
    bid_a: float
    ask_a: float
    bid_b: float
    ask_b: float
    volatility: float


@dataclass(frozen=True)
class Signal:
    side: int  # +1 long spread, -1 short spread, 0 flat
    zscore: float
    beta: float
    required_confirmations: int


class KalmanHedge:
    """Scalar Kalman regression y_t = beta_t x_t + epsilon_t."""

    def __init__(
        self,
        beta0: float = 1.0,
        process_var: float = 1e-5,
        meas_var: float = 1e-3,
        p0: float = 1.0,
    ):
        self.beta = beta0
        self.p = p0
        self.q = process_var
        self.r = meas_var

    def update(self, x: float, y: float) -> float:
        p_pred = self.p + self.q
        denom = p_pred * x * x + self.r
        if denom <= 0.0:
            return self.beta
        gain = p_pred * x / denom
        residual = y - self.beta * x
        self.beta += gain * residual
        self.p = (1.0 - gain * x) * p_pred
        return self.beta


class DynamicDebouncer:
    """Increase confirmation depth as observed volatility increases."""

    def __init__(
        self,
        base: int = 2,
        max_confirmations: int = 8,
        reference_vol: float = 0.002,
    ):
        self.base = base
        self.max_confirmations = max_confirmations
        self.reference_vol = reference_vol
        self.pending = 0
        self.last_side = 0

    def required(self, volatility: float) -> int:
        scale = max(0.0, volatility / max(self.reference_vol, 1e-12))
        return int(np.clip(round(self.base + scale), self.base, self.max_confirmations))

    def update(self, side: int, volatility: float) -> tuple[bool, int]:
        required = self.required(volatility)
        if side == 0:
            self.pending = 0
            self.last_side = 0
            return False, required
        if side != self.last_side:
            self.pending = 1
            self.last_side = side
        else:
            self.pending += 1
        return self.pending >= required, required


@dataclass
class OCOBracket:
    side: int
    entry_spread: float
    reference_notional: float = 100.0
    stop_bps: float = 5.0
    limit_bps: float = 5.0
    active: bool = True
    stop_triggered: bool = False

    def __post_init__(self) -> None:
        adverse = self.reference_notional * self.stop_bps * 1e-4
        self.stop_price = self.entry_spread - self.side * adverse
        self.limit_price = (
            self.stop_price - self.side * self.reference_notional * self.limit_bps * 1e-4
        )
        self.exit_reason: str | None = None

    def check_stop(self, spread: float) -> bool:
        if not self.active:
            return False

        hit = spread <= self.stop_price if self.side > 0 else spread >= self.stop_price
        if not self.stop_triggered:
            if not hit:
                return False
            self.stop_triggered = True
            self.exit_reason = "oco_stop_triggered"

        # After the trigger, the stop-limit becomes a resting limit.
        marketable = spread >= self.limit_price if self.side > 0 else spread <= self.limit_price
        if not marketable:
            return False

        self.exit_reason = "oco_stop_limit"
        self.active = False
        return True

    def cancel_other(self, reason: str = "mean_reversion") -> None:
        self.exit_reason = reason
        self.active = False


class PairStrategy:
    def __init__(self, entry_z: float = 2.0, exit_z: float = 0.5, window: int = 200):
        self.entry_z = entry_z
        self.exit_z = exit_z
        self.window = window
        self.beta = KalmanHedge()
        self.debouncer = DynamicDebouncer()
        self.spreads: deque[float] = deque(maxlen=window)
        self.position = 0
        self.bracket: OCOBracket | None = None
        self.entries = 0
        self.exits = 0
        self.stop_exits = 0

    def update(self, tick: Tick) -> Signal:
        mid_a = 0.5 * (tick.bid_a + tick.ask_a)
        mid_b = 0.5 * (tick.bid_b + tick.ask_b)
        beta = self.beta.update(mid_b, mid_a)
        spread = mid_a - beta * mid_b
        self.spreads.append(spread)

        if len(self.spreads) < max(30, self.window // 4):
            return Signal(0, 0.0, beta, self.debouncer.required(tick.volatility))

        arr = np.fromiter(self.spreads, dtype=float)
        mean = float(arr.mean())
        sd = float(arr.std(ddof=1))
        z = 0.0 if sd <= 1e-12 else (spread - mean) / sd

        if self.bracket is not None:
            if self.bracket.check_stop(spread):
                self.position = 0
                self.exits += 1
                self.stop_exits += 1
                self.bracket = None
            elif not self.bracket.stop_triggered and abs(z) < self.exit_z:
                self.bracket.cancel_other()
                self.position = 0
                self.exits += 1
                self.bracket = None
            return Signal(self.position, z, beta, self.debouncer.required(tick.volatility))

        desired = -1 if z >= self.entry_z else (1 if z <= -self.entry_z else 0)
        confirmed, required = self.debouncer.update(desired, tick.volatility)

        if confirmed:
            self.position = desired
            self.entries += 1
            self.bracket = OCOBracket(
                desired,
                spread,
                reference_notional=abs(mid_a) + abs(beta * mid_b),
            )
            self.debouncer.update(0, tick.volatility)

        return Signal(self.position, z, beta, required)
