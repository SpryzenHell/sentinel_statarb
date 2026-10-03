import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sentinel_statarb.backtest import ExecutionConfig, run


def _parse_pairs(value: str) -> list[tuple[float, float]]:
    pairs = []
    for item in value.split(","):
        commission, slippage = item.split(":", 1)
        pairs.append((float(commission), float(slippage)))
    return pairs


def _parse_ints(value: str) -> list[int]:
    return [int(item) for item in value.split(",") if item.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sweep execution costs and crash locations for Sentinel's synthetic backtest."
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--ticks", type=int, default=50_000)
    parser.add_argument("--crash-at", default="25000")
    parser.add_argument(
        "--cost-pairs",
        default="0:0,0.4:1,1:2,2:5,5:5",
        help="commission_bps:slippage_bps pairs",
    )
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    parser.add_argument("--target-notional", type=float, default=10_000.0)
    args = parser.parse_args()

    crash_locations = _parse_ints(args.crash_at)
    cost_pairs = _parse_pairs(args.cost_pairs)
    results = []

    for crash_at in crash_locations:
        for commission_bps, slippage_bps in cost_pairs:
            execution = ExecutionConfig(
                initial_cash=args.initial_cash,
                target_gross_notional=args.target_notional,
                commission_bps=commission_bps,
                slippage_bps=slippage_bps,
            )
            baseline = run(
                seed=args.seed,
                n=args.ticks,
                crash_at=crash_at,
                dynamic=False,
                execution=execution,
            )
            dynamic = run(
                seed=args.seed,
                n=args.ticks,
                crash_at=crash_at,
                dynamic=True,
                execution=execution,
            )
            results.append(
                {
                    "crash_at": crash_at,
                    "commission_bps": commission_bps,
                    "slippage_bps": slippage_bps,
                    "baseline": baseline.__dict__,
                    "dynamic": dynamic.__dict__,
                    "dynamic_minus_baseline": {
                        "pnl": dynamic.pnl - baseline.pnl,
                        "max_drawdown": dynamic.max_drawdown - baseline.max_drawdown,
                        "flash_crash_loss": (
                            dynamic.flash_crash_loss - baseline.flash_crash_loss
                        ),
                        "turnover": dynamic.turnover - baseline.turnover,
                    },
                }
            )

    output = {
        "seed": args.seed,
        "ticks": args.ticks,
        "initial_cash": args.initial_cash,
        "target_notional": args.target_notional,
        "claim_note": (
            "Synthetic deterministic sensitivity analysis. Execution costs are "
            "user-specified assumptions, not venue fee schedules or live-market results."
        ),
        "results": results,
    }
    path = ROOT / "results" / "backtest_sensitivity.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
