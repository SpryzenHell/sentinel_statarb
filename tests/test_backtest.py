import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "python"))

from sentinel_statarb.backtest import ExecutionConfig, PaperPortfolio, generate_path, run


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


def test_backtest_result_reports_non_negative_crash_loss():
    result = run(seed=9, n=80, crash_at=40, dynamic=True)
    assert result.flash_crash_loss >= 0.0


def test_generate_path_rejects_invalid_crash_index():
    with pytest.raises(ValueError, match="crash_at"):
        generate_path(seed=9, n=80, crash_at=80)
