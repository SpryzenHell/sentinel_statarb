import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "python"))

from sentinel_statarb.backtest import (
    ExecutionConfig,
    PaperPortfolio,
    generate_path,
    run,
    run_ticks,
)


def test_portfolio_uses_two_leg_cash_accounting_and_costs():
    tick = generate_path(seed=3, n=2)[0]
    p = PaperPortfolio(
        ExecutionConfig(
            initial_cash=1_000_000.0,
            target_gross_notional=10_000.0,
            commission_bps=0.40,
            slippage_bps=1.00,
        )
    )
    before = p.equity(tick)
    p.enter_spread(1, 1.0, tick)

    assert p.position_a > 0.0
    assert p.position_b < 0.0
    assert p.turnover > 0.0
    assert p.fees > 0.0
    assert p.spread_cost > 0.0
    assert p.slippage_cost > 0.0
    assert p.max_gross_exposure == pytest.approx(10_000.0, rel=0.01)

    p.exit_spread(tick)
    assert p.position_a == 0.0
    assert p.position_b == 0.0
    assert p.equity(tick) < before


def test_backtest_accounts_for_execution_costs():
    free = run(
        seed=7,
        n=4_000,
        crash_at=2_000,
        dynamic=True,
        execution=ExecutionConfig(commission_bps=0.0, slippage_bps=0.0),
    )
    costly = run(
        seed=7,
        n=4_000,
        crash_at=2_000,
        dynamic=True,
        execution=ExecutionConfig(commission_bps=5.0, slippage_bps=5.0),
    )

    assert costly.turnover == pytest.approx(free.turnover, rel=0.05, abs=1e-6)
    assert costly.fees > free.fees
    assert costly.spread_cost == pytest.approx(free.spread_cost, rel=1e-9, abs=1e-9)
    assert costly.slippage_cost > free.slippage_cost
    assert costly.pnl < free.pnl


def test_backtest_is_flat_after_final_liquidation_and_metrics_are_sane():
    execution = ExecutionConfig(commission_bps=0.40, slippage_bps=1.00)
    result = run(
        seed=7,
        n=4_000,
        crash_at=2_000,
        dynamic=True,
        execution=execution,
    )
    assert math.isfinite(result.pnl)
    assert result.trades_entered >= result.exits
    assert result.turnover >= 0.0
    assert result.fees >= 0.0
    assert result.spread_cost >= 0.0
    assert result.slippage_cost >= 0.0
    assert result.max_gross_exposure >= result.max_net_exposure >= 0.0
    assert result.total_cost == pytest.approx(
        result.fees + result.spread_cost + result.slippage_cost
    )
    assert result.return_pct == pytest.approx(result.pnl / execution.initial_cash * 100.0)
    assert result.max_drawdown_pct <= 0.0
    assert math.isfinite(result.best_trade_pnl)
    assert math.isfinite(result.worst_trade_pnl)


def test_nonzero_execution_delay_is_recorded():
    ticks = generate_path(seed=7, n=1200, crash_at=600)
    immediate = run_ticks(iter(ticks), dynamic=True, seed=7, crash_at=600, execution_delay_ticks=0)
    delayed = run_ticks(iter(ticks), dynamic=True, seed=7, crash_at=600, execution_delay_ticks=1)

    assert immediate.execution_delay_ticks == 0
    assert delayed.execution_delay_ticks == 1
    assert math.isfinite(immediate.pnl)
    assert math.isfinite(delayed.pnl)


def test_negative_execution_delay_is_rejected():
    with pytest.raises(ValueError, match="execution_delay_ticks"):
        run_ticks([], execution_delay_ticks=-1)


def test_strategy_parameter_validation_is_enforced():
    ticks = generate_path(seed=7, n=100)
    with pytest.raises(ValueError, match="entry_z"):
        run_ticks(ticks, entry_z=0.0)
    with pytest.raises(ValueError, match="exit_z"):
        run_ticks(ticks, entry_z=2.0, exit_z=2.0)
    with pytest.raises(ValueError, match="window"):
        run_ticks(ticks, window=1)


def test_run_ticks_accepts_streaming_iterables():
    ticks = generate_path(seed=5, n=500, crash_at=250)
    result = run_ticks(iter(ticks), dynamic=True, seed=-1, crash_at=250)
    assert result.ticks == 500
    assert math.isfinite(result.pnl)
    assert result.max_gross_exposure >= 0.0


def test_backtest_result_reports_non_negative_crash_loss():
    result = run(seed=9, n=80, crash_at=40, dynamic=True)
    assert result.flash_crash_loss >= 0.0


def test_generate_path_rejects_invalid_crash_index():
    with pytest.raises(ValueError, match="crash_at"):
        generate_path(seed=9, n=80, crash_at=80)
