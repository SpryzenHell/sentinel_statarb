import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sentinel_statarb.backtest import ExecutionConfig, run


def _ints(value: str) -> list[int]:
    return [int(x) for x in value.split(",") if x.strip()]


def _floats(value: str) -> list[float]:
    return [float(x) for x in value.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Sentinel robustness sweeps across seeds and crash locations."
    )
    parser.add_argument("--seeds", default="3,7,11,17,23")
    parser.add_argument("--ticks", type=int, default=20_000)
    parser.add_argument(
        "--crash-fractions",
        default="0.25,0.50,0.75",
        help="Fractions of the generated path at which to inject the crash.",
    )
    parser.add_argument("--commission-bps", type=float, default=0.40)
    parser.add_argument("--slippage-bps", type=float, default=1.00)
    parser.add_argument("--target-notional", type=float, default=10_000.0)
    parser.add_argument("--initial-cash", type=float, default=1_000_000.0)
    args = parser.parse_args()

    seeds = _ints(args.seeds)
    fractions = _floats(args.crash_fractions)
    if args.ticks <= 1:
        raise SystemExit("--ticks must be greater than one")
    if not seeds:
        raise SystemExit("--seeds must not be empty")

    execution = ExecutionConfig(
        initial_cash=args.initial_cash,
        target_gross_notional=args.target_notional,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
    )

    cases = []
    for seed in seeds:
        for fraction in fractions:
            crash_at = min(args.ticks - 1, max(0, int(round(fraction * (args.ticks - 1)))))
            baseline = run(
                seed=seed,
                n=args.ticks,
                crash_at=crash_at,
                dynamic=False,
                execution=execution,
            )
            dynamic = run(
                seed=seed,
                n=args.ticks,
                crash_at=crash_at,
                dynamic=True,
                execution=execution,
            )
            cases.append(
                {
                    "seed": seed,
                    "crash_fraction": fraction,
                    "crash_at": crash_at,
                    "baseline": baseline.__dict__,
                    "dynamic": dynamic.__dict__,
                    "protection_delta": {
                        "pnl": dynamic.pnl - baseline.pnl,
                        "max_drawdown": dynamic.max_drawdown - baseline.max_drawdown,
                        "flash_crash_loss": dynamic.flash_crash_loss - baseline.flash_crash_loss,
                        "trades_entered": dynamic.trades_entered - baseline.trades_entered,
                    },
                }
            )

    pnl_deltas = [x["protection_delta"]["pnl"] for x in cases]
    dd_deltas = [x["protection_delta"]["max_drawdown"] for x in cases]
    crash_deltas = [x["protection_delta"]["flash_crash_loss"] for x in cases]

    summary = {
        "cases": len(cases),
        "positive_pnl_delta_fraction": sum(x > 0 for x in pnl_deltas) / len(pnl_deltas),
        "mean_pnl_delta": statistics.fmean(pnl_deltas),
        "median_pnl_delta": statistics.median(pnl_deltas),
        "mean_drawdown_delta": statistics.fmean(dd_deltas),
        "mean_flash_crash_loss_delta": statistics.fmean(crash_deltas),
        "best_pnl_delta": max(pnl_deltas),
        "worst_pnl_delta": min(pnl_deltas),
    }

    payload = {
        "execution": execution.__dict__,
        "seeds": seeds,
        "ticks": args.ticks,
        "crash_fractions": fractions,
        "summary": summary,
        "cases": cases,
        "claim_note": (
            "Synthetic robustness sweep across fixed random seeds and injected crash "
            "locations. Results are scenario analysis, not live-market performance."
        ),
    }

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / "backtest_robustness.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
