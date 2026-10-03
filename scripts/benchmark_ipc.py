import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
import struct

import zmq

ROOT = Path(__file__).parents[1]
TICK_FMT = "<BQQddddd"
ORDER_FMT = "<BbHQQd"


def pack_tick(seq: int, ts_ns: int) -> bytes:
    return struct.pack(TICK_FMT, 1, seq, ts_ns, 100.0, 100.01, 100.0, 100.01, 0.001)


def pack_order(order_id: int, side: int, ts_ns: int) -> bytes:
    return struct.pack(ORDER_FMT, 2, side, 0, order_id, ts_ns, 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--orders", type=int, default=10_000)
    args = parser.parse_args()

    exe = ROOT / "build" / "sentinel" / "sentinel_exec"
    if not exe.exists():
        raise SystemExit("Build sentinel_exec first (requires libzmq3-dev).")

    endpoint = f"ipc:///tmp/sentinel_e2e_{os.getpid()}"
    reports_endpoint = endpoint + ".reports"
    proc = subprocess.Popen(
        [str(exe), endpoint],
        stderr=subprocess.PIPE,
        text=True,
    )

    ctx = zmq.Context()
    push = ctx.socket(zmq.PUSH)
    pull = ctx.socket(zmq.PULL)
    push.connect(endpoint)
    pull.connect(reports_endpoint)
    time.sleep(0.1)

    started = time.perf_counter()
    reports = 0

    for i in range(args.orders):
        ts = time.monotonic_ns()
        push.send(pack_tick(i, ts))
        push.send(pack_order(i, 1, ts))
        pull.recv()
        reports += 1

    push.send(struct.pack("<B", 3))
    proc.wait(timeout=5)

    elapsed = time.perf_counter() - started
    push.close()
    pull.close()
    ctx.term()

    result = {
        "orders": args.orders,
        "execution_reports": reports,
        "elapsed_s": elapsed,
        "orders_per_sec": args.orders / elapsed,
        "transport": "ZeroMQ IPC",
    }
    path = ROOT / "results" / "ipc_e2e.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
