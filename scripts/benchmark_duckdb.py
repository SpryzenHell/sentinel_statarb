import argparse
import json
import queue
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticks", type=int, default=10_000_000)
    parser.add_argument("--batch", type=int, default=100_000)
    parser.add_argument("--db", default="results/ticks.duckdb")
    args = parser.parse_args()

    try:
        import duckdb
    except ImportError as exc:
        raise SystemExit(
            "DuckDB is required: install the project with pip install -e '.[full]'"
        ) from exc

    root = Path(__file__).parents[1]
    db = root / args.db
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()

    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE ticks("
        "ts_ns BIGINT, bid DOUBLE, ask DOUBLE, size DOUBLE)"
    )

    work = queue.Queue(maxsize=8)
    sentinel = object()
    rng = np.random.default_rng(13)
    produced = 0

    def writer() -> None:
        while True:
            item = work.get()
            if item is sentinel:
                work.task_done()
                return
            con.register("batch_view", item)
            con.execute("INSERT INTO ticks SELECT * FROM batch_view")
            con.unregister("batch_view")
            work.task_done()

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    started = time.perf_counter()

    while produced < args.ticks:
        count = min(args.batch, args.ticks - produced)
        ts = np.arange(produced, produced + count, dtype=np.int64)
        mid = 100.0 + np.cumsum(rng.normal(0.0, 0.001, count))
        batch = pd.DataFrame({
            "ts_ns": ts,
            "bid": mid - 0.005,
            "ask": mid + 0.005,
            "size": rng.lognormal(0.0, 0.4, count),
        })
        work.put(batch)
        produced += count

    work.put(sentinel)
    work.join()
    thread.join()

    elapsed = time.perf_counter() - started
    rows = int(con.execute("SELECT COUNT(*) FROM ticks").fetchone()[0])
    con.close()

    result = {
        "requested_ticks": args.ticks,
        "rows_written": rows,
        "elapsed_s": elapsed,
        "rows_per_sec": rows / elapsed,
        "async_writer": True,
        "backend": "duckdb",
    }
    path = root / "results" / "duckdb_benchmark.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
