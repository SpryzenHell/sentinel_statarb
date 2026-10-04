import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "python"))

from sentinel_statarb.backtest import generate_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a small DuckDB database for the Sentinel replay demo."
    )
    parser.add_argument("--ticks", type=int, default=5000)
    parser.add_argument("--db", default="results/sample_telemetry.duckdb")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    if args.ticks <= 0:
        raise SystemExit("--ticks must be positive")

    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit(
            "DuckDB is required. Install with: pip install -e '.[full]'"
        ) from exc

    ticks = generate_path(seed=args.seed, n=args.ticks, crash_at=max(100, args.ticks // 2))

    root = ROOT
    db = root / args.db
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()

    with duckdb.connect(str(db)) as con:
        con.execute(
            """
            CREATE TABLE ticks (
                seq BIGINT,
                ts_ns BIGINT,
                bid_a DOUBLE,
                ask_a DOUBLE,
                bid_b DOUBLE,
                ask_b DOUBLE,
                volatility DOUBLE
            )
            """
        )
        rows = [
            (
                i,
                tick.ts_ns,
                tick.bid_a,
                tick.ask_a,
                tick.bid_b,
                tick.ask_b,
                tick.volatility,
            )
            for i, tick in enumerate(ticks)
        ]
        con.executemany(
            "INSERT INTO ticks VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        count = int(con.execute("SELECT COUNT(*) FROM ticks").fetchone()[0])

    print(f"database={db}")
    print(f"rows={count}")
    print(f"seed={args.seed}")


if __name__ == "__main__":
    main()
