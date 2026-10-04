import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sentinel_statarb.backtest import ExecutionConfig, run


def _floats(value: str) -> list[float]:
    return [float(x) for x in value.split(",") if x.strip()]


def _ints(value: str) -> list[int]:
    return [int(x) for x in value.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep Sentinel strategy thresholds and rolling window."
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ticks", type=int, default=20_000)
    parser.add_argument("--crash-at", type=int, default=None)
    parser.add_argument("--entry-zs", default="1.5,2.0,2.5,3.0")
    parser.add_argument("--exit-zs", default="0.25,0.5,0.75")
    parser.add_argument("--windows", default="100,200,400")
    parser.add_argument("--commission-bps", type=float, default=0.40)
    parser.add_argument("--slippage-bps", type=float, default=1.00)
    parser.add_argument("--target-notional", type=float, default=10_000.0)
    parser.add_argument("--execution-delay-ticks", type=int, default=1)
    args = parser.parse_args()

    entry_zs = _floats(args.entry_zs)
    exit_zs = _floats(args.exit_zs)
    windows = _ints(args.windows)
    crash_at = args.crash_at if args.crash_at is not None else args.ticks // 2

    execution = ExecutionConfig(
        target_gross_notional=args.target_notional,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
    )

    results = []
    for entry_z in entry_zs:
        for exit_z in exit_zs:
            if exit_z >= entry_z:
                continue
            for window in windows:
                baseline = run(
                    seed=args.seed,
                    n=args.ticks,
                    crash_at=crash_at,
                    dynamic=False,
                    execution=execution,
                    execution_delay_ticks=args.execution_delay_ticks,
                    entry_z=entry_z,
                    exit_z=exit_z,
                    window=window,
                )
                dynamic = run(
                    seed=args.seed,
                    n=args.ticks,
                    crash_at=crash_at,
                    dynamic=True,
                    execution=execution,
                    execution_delay_ticks=args.execution_delay_ticks,
                    entry_z=entry_z,
                    exit_z=exit_z,
                    window=window,
                )
                results.append(
                    {
                        "entry_z": entry_z,
                        "exit_z": exit_z,
                        "window": window,
                        "baseline": baseline.__dict__,
                        "dynamic": dynamic.__dict__,
                        "dynamic_minus_baseline": {
                            "pnl": dynamic.pnl - baseline.pnl,
                            "max_drawdown": dynamic.max_drawdown - baseline.max_drawdown,
                            "flash_crash_loss": dynamic.flash_crash_loss - baseline.flash_crash_loss,
                            "trades_entered": dynamic.trades_entered - baseline.trades_entered,
                        },
                    }
                )

    results.sort(key=lambda x: x["dynamic"]["pnl"], reverse=True)
    payload = {
        "seed": args.seed,
        "ticks": args.ticks,
        "crash_at": crash_at,
        "execution": execution.__dict__,
        "execution_delay_ticks": args.execution_delay_ticks,
        "grid": {
            "entry_zs": entry_zs,
            "exit_zs": exit_zs,
            "windows": windows,
        },
        "results": results,
        "claim_note": (
            "Synthetic parameter sensitivity only. Ranking depends on the generated "
            "scenario and execution assumptions; it is not live-market evidence."
        ),
    }

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / "backtest_parameter_sensitivity.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
