import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sentinel_statarb.backtest import ExecutionConfig, run_ticks
from sentinel_statarb.strategy import Tick


def _load_ticks(db_path: Path, table: str, limit: int | None) -> list[Tick]:
    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit("DuckDB is required; install with: pip install -e '.[storage]'") from exc

    query = f"""
        SELECT seq, ts_ns, bid_a, ask_a, bid_b, ask_b, volatility
        FROM "{table}"
        ORDER BY seq
    """
    if limit is not None:
        query += f" LIMIT {int(limit)}"

    with duckdb.connect(str(db_path), read_only=True) as con:
        rows = con.execute(query).fetchall()

    return [
        Tick(
            ts_ns=int(row[1]),
            bid_a=float(row[2]),
            ask_a=float(row[3]),
            bid_b=float(row[4]),
            ask_b=float(row[5]),
            volatility=float(row[6]),
        )
        for row in rows
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Sentinel ticks stored in DuckDB.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--table", default="ticks")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--commission-bps", type=float, default=0.40)
    parser.add_argument("--slippage-bps", type=float, default=1.00)
    parser.add_argument("--target-notional", type=float, default=10_000.0)
    args = parser.parse_args()

    ticks = _load_ticks(args.db, args.table, args.limit)
    execution = ExecutionConfig(
        target_gross_notional=args.target_notional,
        commission_bps=args.commission_bps,
        slippage_bps=args.slippage_bps,
    )

    baseline = run_ticks(ticks, dynamic=False, execution=execution, seed=-1)
    dynamic = run_ticks(ticks, dynamic=True, execution=execution, seed=-1)

    import json

    payload = {
        "db": str(args.db),
        "table": args.table,
        "ticks_loaded": len(ticks),
        "execution": execution.__dict__,
        "baseline": baseline.__dict__,
        "dynamic": dynamic.__dict__,
        "dynamic_minus_baseline": {
            "pnl": dynamic.pnl - baseline.pnl,
            "max_drawdown": dynamic.max_drawdown - baseline.max_drawdown,
            "turnover": dynamic.turnover - baseline.turnover,
        },
        "claim_note": (
            "Replay of persisted tick telemetry. Results depend on the stored dataset "
            "and configured paper-execution assumptions; they are not live performance."
        ),
    }

    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    path = out / "duckdb_replay.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
