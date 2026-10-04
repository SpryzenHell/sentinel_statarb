import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sentinel_statarb.backtest import ExecutionConfig, run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Sentinel synthetic stat-arb backtest.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ticks", type=int, default=50_000)
    parser.add_argument("--crash-at", type=int, default=None)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--target-notional", type=float, default=10_000.0)
    parser.add_argument("--commission-bps", type=float, default=0.40)
    parser.add_argument("--slippage-bps", type=float, default=1.00)
    parser.add_argument("--execution-delay-ticks", type=int, default=1)
    parser.add_argument("--entry-z", type=float, default=2.0)
    parser.add_argument("--exit-z", type=float, default=0.5)
    parser.add_argument("--window", type=int, default=200)
    args = parser.parse_args()

    if args.execution_delay_ticks < 0:
        raise SystemExit("--execution-delay-ticks must be non-negative")

    crash_at = args.crash_at if args.crash_at is not None else args.ticks // 2

    execution = ExecutionConfig(
        initial_cash=args.initial_cash,
        target_gross_notional=args.target_notional,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
    )

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    baseline = run(
        seed=args.seed,
        n=args.ticks,
        crash_at=crash_at,
        dynamic=False,
        execution=execution,
        execution_delay_ticks=args.execution_delay_ticks,
        entry_z=args.entry_z,
        exit_z=args.exit_z,
        window=args.window,
    )
    dynamic = run(
        seed=args.seed,
        n=args.ticks,
        crash_at=args.crash_at,
        dynamic=True,
        execution=execution,
        execution_delay_ticks=args.execution_delay_ticks,
        entry_z=args.entry_z,
        exit_z=args.exit_z,
        window=args.window,
    )
    payload = {
        "execution": execution.__dict__,
        "execution_delay_ticks": args.execution_delay_ticks,
        "crash_at": crash_at,
        "strategy": {"entry_z": args.entry_z, "exit_z": args.exit_z, "window": args.window},
        "baseline": baseline.__dict__,
        "dynamic": dynamic.__dict__,
        "delta_pnl": dynamic.pnl - baseline.pnl,
        "delta_flash_crash_loss": dynamic.flash_crash_loss - baseline.flash_crash_loss,
        "claim_note": (
            "Synthetic deterministic path with two-leg bid/ask execution, "
            "configurable commissions/slippage, and a configurable signal-to-fill delay; "
            "values are benchmark outputs, not live-market performance."
        ),
    }
    path = out / "backtest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
