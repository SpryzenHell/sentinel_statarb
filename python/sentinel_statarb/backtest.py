from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

import numpy as np

from .strategy import PairStrategy, Tick


@dataclass(frozen=True)
class ExecutionConfig:
    initial_cash: float = 1_000_000.0
    target_gross_notional: float = 10_000.0
    commission_bps: float = 0.40
    slippage_bps: float = 1.00


@dataclass(frozen=True)
class BacktestResult:
    label: str
    seed: int
    ticks: int
    execution_delay_ticks: int
    trades_entered: int
    exits: int
    stop_exits: int
    mean_reversion_exits: int
    oco_stop_limit_exits: int
    pnl: float
    return_pct: float
    max_drawdown: float
    max_drawdown_pct: float
    flash_crash_loss: float
    fees: float
    spread_cost: float
    slippage_cost: float
    total_cost: float
    turnover: float
    max_gross_exposure: float
    max_net_exposure: float
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_trade_pnl: float
    best_trade_pnl: float
    worst_trade_pnl: float
    profit_factor: float


class PaperPortfolio:
    """Two-leg cash-and-position accounting for the A/B spread."""

    def __init__(self, config: ExecutionConfig):
        if config.initial_cash <= 0.0:
            raise ValueError("initial_cash must be positive")
        if config.target_gross_notional <= 0.0:
            raise ValueError("target_gross_notional must be positive")
        if config.commission_bps < 0.0 or config.slippage_bps < 0.0:
            raise ValueError("cost parameters must be non-negative")
        self.config = config
        self.cash = config.initial_cash
        self.position_a = 0.0
        self.position_b = 0.0
        self.fees = 0.0
        self.spread_cost = 0.0
        self.slippage_cost = 0.0
        self.turnover = 0.0
        self.trade_count = 0
        self.max_gross_exposure = 0.0
        self.max_net_exposure = 0.0

    @staticmethod
    def _mid(bid: float, ask: float) -> float:
        if not (np.isfinite(bid) and np.isfinite(ask) and bid > 0.0 and ask >= bid):
            raise ValueError("invalid market quote")
        return 0.5 * (bid + ask)

    def equity(self, tick: Tick) -> float:
        mid_a = self._mid(tick.bid_a, tick.ask_a)
        mid_b = self._mid(tick.bid_b, tick.ask_b)
        return self.cash + self.position_a * mid_a + self.position_b * mid_b

    def exposures(self, tick: Tick) -> tuple[float, float]:
        mid_a = self._mid(tick.bid_a, tick.ask_a)
        mid_b = self._mid(tick.bid_b, tick.ask_b)
        gross = abs(self.position_a * mid_a) + abs(self.position_b * mid_b)
        net = abs(self.position_a * mid_a + self.position_b * mid_b)
        self.max_gross_exposure = max(self.max_gross_exposure, gross)
        self.max_net_exposure = max(self.max_net_exposure, net)
        return gross, net

    def _fill_leg(self, side: int, qty: float, bid: float, ask: float) -> None:
        if qty <= 0.0:
            return
        mid = self._mid(bid, ask)
        slip = self.config.slippage_bps * 1e-4
        quote_price = ask if side > 0 else bid
        price = quote_price * (1.0 + slip) if side > 0 else quote_price * (1.0 - slip)

        notional = qty * price
        fee = notional * self.config.commission_bps * 1e-4
        self.cash -= side * notional
        self.cash -= fee
        self.fees += fee
        self.turnover += notional
        self.spread_cost += qty * abs(quote_price - mid)
        self.slippage_cost += qty * abs(price - quote_price)

    def enter_spread(self, side: int, beta: float, tick: Tick) -> float:
        if side not in (-1, 1):
            raise ValueError("spread entry side must be -1 or +1")
        if beta == 0.0 or not np.isfinite(beta):
            raise ValueError("beta must be finite and non-zero")
        if self.position_a != 0.0 or self.position_b != 0.0:
            raise ValueError("cannot enter while already positioned")

        mid_a = self._mid(tick.bid_a, tick.ask_a)
        mid_b = self._mid(tick.bid_b, tick.ask_b)
        qty_a = self.config.target_gross_notional / (mid_a + abs(beta) * mid_b)
        target_a = side * qty_a
        target_b = -side * beta * qty_a

        self._fill_leg(1 if target_a > 0.0 else -1, abs(target_a), tick.bid_a, tick.ask_a)
        self._fill_leg(1 if target_b > 0.0 else -1, abs(target_b), tick.bid_b, tick.ask_b)
        self.position_a = target_a
        self.position_b = target_b
        self.trade_count += 1
        self.exposures(tick)
        return self.equity(tick)

    def exit_spread(self, tick: Tick) -> float:
        if self.position_a == 0.0 and self.position_b == 0.0:
            return self.equity(tick)

        close_a = -self.position_a
        close_b = -self.position_b
        self._fill_leg(1 if close_a > 0.0 else -1, abs(close_a), tick.bid_a, tick.ask_a)
        self._fill_leg(1 if close_b > 0.0 else -1, abs(close_b), tick.bid_b, tick.ask_b)
        self.position_a = 0.0
        self.position_b = 0.0
        self.exposures(tick)
        return self.equity(tick)


@dataclass
class _OpenTrade:
    equity_before_entry: float


def generate_path(
    seed: int = 7,
    n: int = 50_000,
    crash_at: int | None = None,
) -> List[Tick]:
    if n <= 0:
        raise ValueError("n must be positive")
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
        if not 0 <= crash_at < n:
            raise ValueError("crash_at must be inside the generated path")
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


def run_ticks(
    ticks: Iterable[Tick],
    *,
    dynamic: bool = True,
    execution: ExecutionConfig | None = None,
    execution_delay_ticks: int = 1,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    window: int = 200,
    seed: int = -1,
    crash_at: int | None = None,
) -> BacktestResult:
    """Run strategy and portfolio accounting on an ordered, streamable Tick iterable.

    Signals generated at tick t are scheduled for execution at t + execution_delay_ticks.
    The default one-tick delay prevents same-quote signal/fill lookahead.
    """

    if execution_delay_ticks < 0:
        raise ValueError("execution_delay_ticks must be non-negative")
    if entry_z <= 0.0:
        raise ValueError("entry_z must be positive")
    if exit_z < 0.0 or exit_z >= entry_z:
        raise ValueError("exit_z must be non-negative and less than entry_z")
    if window < 2:
        raise ValueError("window must be at least 2")
    if crash_at is not None and crash_at < 0:
        raise ValueError("crash_at must be non-negative")

    strategy = PairStrategy(entry_z=entry_z, exit_z=exit_z, window=window)
    if not dynamic:
        strategy.debouncer.base = 1
        strategy.debouncer.max_confirmations = 1
        strategy.debouncer.reference_vol = 1.0

    portfolio = PaperPortfolio(execution or ExecutionConfig())
    trade_pnls: list[float] = []
    open_trade: _OpenTrade | None = None
    scheduled: dict[int, tuple[int, float]] = {}

    count = 0
    last_tick: Tick | None = None
    last_equity = portfolio.config.initial_cash
    peak_equity = last_equity
    min_drawdown = 0.0
    crash_pre_equity: float | None = None
    crash_low: float | None = None

    def execute_target(target: int, beta: float, tick: Tick) -> None:
        nonlocal open_trade
        current = 0 if portfolio.position_a == 0.0 else (1 if portfolio.position_a > 0.0 else -1)

        if current == 0 and target != 0:
            before = portfolio.equity(tick)
            portfolio.enter_spread(target, beta, tick)
            open_trade = _OpenTrade(before)
        elif current != 0 and target == 0:
            portfolio.exit_spread(tick)
            if open_trade is not None:
                trade_pnls.append(portfolio.equity(tick) - open_trade.equity_before_entry)
            open_trade = None
        elif current != 0 and target != 0 and current != target:
            portfolio.exit_spread(tick)
            if open_trade is not None:
                trade_pnls.append(portfolio.equity(tick) - open_trade.equity_before_entry)
            before = portfolio.equity(tick)
            portfolio.enter_spread(target, beta, tick)
            open_trade = _OpenTrade(before)

    for tick in ticks:
        if crash_at == count == 0:
            crash_pre_equity = portfolio.equity(tick)

        scheduled_action = scheduled.pop(count, None)
        if scheduled_action is not None:
            execute_target(scheduled_action[0], scheduled_action[1], tick)

        previous_position = strategy.position
        strategy.update(tick)
        current_position = strategy.position

        if current_position != previous_position:
            due = count + execution_delay_ticks
            if execution_delay_ticks == 0:
                execute_target(current_position, strategy.beta.beta, tick)
            else:
                scheduled[due] = (current_position, strategy.beta.beta)

        portfolio.exposures(tick)
        last_equity = portfolio.equity(tick)
        peak_equity = max(peak_equity, last_equity)
        min_drawdown = min(min_drawdown, last_equity - peak_equity)

        if crash_at is not None:
            if count == crash_at - 1:
                crash_pre_equity = last_equity
            if crash_at <= count <= crash_at + 45:
                crash_low = (
                    last_equity if crash_low is None else min(crash_low, last_equity)
                )

        last_tick = tick
        count += 1

    if last_tick is None:
        raise ValueError("ticks must contain at least one observation")

    if crash_at is not None:
        if crash_at >= count:
            raise ValueError("crash_at must be inside the supplied ticks")
        if crash_pre_equity is None:
            crash_pre_equity = last_equity
        if crash_low is None:
            crash_low = last_equity
    else:
        crash_pre_equity = None
        crash_low = None

    if open_trade is not None:
        portfolio.exit_spread(last_tick)
        trade_pnls.append(portfolio.equity(last_tick) - open_trade.equity_before_entry)
        last_equity = portfolio.equity(last_tick)
        peak_equity = max(peak_equity, last_equity)
        min_drawdown = min(min_drawdown, last_equity - peak_equity)
        if crash_at is not None and crash_at <= count - 1 <= crash_at + 45:
            crash_low = last_equity if crash_low is None else min(crash_low, last_equity)

    flash_crash_loss = (
        0.0
        if crash_at is None
        else max(0.0, float(crash_pre_equity) - float(crash_low))
    )

    wins = sum(1 for pnl in trade_pnls if pnl > 0.0)
    losses = sum(1 for pnl in trade_pnls if pnl < 0.0)
    total_pnl = portfolio.equity(last_tick) - portfolio.config.initial_cash
    initial_cash = portfolio.config.initial_cash
    max_drawdown_pct = (min_drawdown / initial_cash) * 100.0
    return_pct = (total_pnl / initial_cash) * 100.0
    gross_profit = sum(p for p in trade_pnls if p > 0.0)
    gross_loss = -sum(p for p in trade_pnls if p < 0.0)
    profit_factor = gross_profit / gross_loss if gross_loss > 0.0 else float("inf")
    best_trade = max(trade_pnls) if trade_pnls else 0.0
    worst_trade = min(trade_pnls) if trade_pnls else 0.0

    return BacktestResult(
        label="dynamic" if dynamic else "baseline",
        seed=seed,
        ticks=count,
        execution_delay_ticks=execution_delay_ticks,
        trades_entered=portfolio.trade_count,
        exits=len(trade_pnls),
        stop_exits=strategy.stop_exits,
        mean_reversion_exits=max(0, strategy.exits - strategy.stop_exits),
        oco_stop_limit_exits=strategy.stop_exits,
        pnl=float(total_pnl),
        return_pct=float(return_pct),
        max_drawdown=float(min_drawdown),
        max_drawdown_pct=float(max_drawdown_pct),
        flash_crash_loss=float(flash_crash_loss),
        fees=float(portfolio.fees),
        spread_cost=float(portfolio.spread_cost),
        slippage_cost=float(portfolio.slippage_cost),
        total_cost=float(portfolio.fees + portfolio.spread_cost + portfolio.slippage_cost),
        turnover=float(portfolio.turnover),
        max_gross_exposure=float(portfolio.max_gross_exposure),
        max_net_exposure=float(portfolio.max_net_exposure),
        winning_trades=wins,
        losing_trades=losses,
        win_rate=float(wins / len(trade_pnls)) if trade_pnls else 0.0,
        avg_trade_pnl=float(np.mean(trade_pnls)) if trade_pnls else 0.0,
        best_trade_pnl=float(best_trade),
        worst_trade_pnl=float(worst_trade),
        profit_factor=float(profit_factor),
    )

def run(
    seed: int = 7,
    n: int = 50_000,
    crash_at: int | None = None,
    dynamic: bool = True,
    execution: ExecutionConfig | None = None,
    execution_delay_ticks: int = 1,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    window: int = 200,
) -> BacktestResult:
    ticks = generate_path(seed, n, crash_at)
    return run_ticks(
        ticks,
        dynamic=dynamic,
        execution=execution,
        execution_delay_ticks=execution_delay_ticks,
        entry_z=entry_z,
        exit_z=exit_z,
        window=window,
        seed=seed,
        crash_at=crash_at,
    )
