import argparse
import json
import os
import struct
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import zmq

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "python"))
from sentinel_statarb.backtest import generate_path
from sentinel_statarb.strategy import PairStrategy

TICK_FMT = "<BQQddddd"
ORDER_FMT = "<BbHQd"

def pack_tick(tick, seq):
    return struct.pack(TICK_FMT, 1, seq, tick.ts_ns, tick.bid_a, tick.ask_a, tick.bid_b, tick.ask_b, tick.volatility)

def pack_order(order_id, side, qty=1.0):
    return struct.pack(ORDER_FMT, 2, side, 0, order_id, time.monotonic_ns(), qty)

def main():
    ap = argparse.ArgumentParser(description="Replay synthetic ticks through Python strategy and C++ execution engine")
    ap.add_argument("--ticks", type=int, default=5000)
    args = ap.parse_args()

    exe = ROOT / "build" / "sentinel" / "sentinel_exec"
    if not exe.exists(): raise SystemExit("Build sentinel_exec first (requires libzmq3-dev).")

    endpoint = f"ipc:///tmp/sentinel_replay_{os.getpid()}.ipc"
    proc = subprocess.Popen([str(exe), endpoint], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ctx = zmq.Context()
    push = ctx.socket(zmq.PUSH)
    pull = ctx.socket(zmq.PULL)
    pull.setsockopt(zmq.RCVTIMEO, 3000)
    push.connect(endpoint)
    pull.connect(endpoint + ".reports")
    time.sleep(0.1)

    strategy = PairStrategy()
    previous_position = 0
    order_id = 0
    reports = []
    start = time.perf_counter()

    for seq, tick in enumerate(generate_path(seed=7, n=args.ticks, crash_at=max(100, args.ticks // 2)), start=1):
        tick = replace(tick, ts_ns=time.monotonic_ns())
        push.send(pack_tick(tick, seq))
        signal = strategy.update(tick)
        if signal.side != previous_position:
            if previous_position != 0:
                order_id += 1; push.send(pack_order(order_id, -previous_position)); reports.append(pull.recv())
            if signal.side != 0:
                order_id += 1; push.send(pack_order(order_id, signal.side)); reports.append(pull.recv())
            previous_position = signal.side

    push.send(b"\x03")
    proc.wait(timeout=5)
    elapsed = time.perf_counter() - start
    stderr = proc.stderr.read().strip()
    push.close(); pull.close(); ctx.term()

    status_counts = {}
    for report in reports:
        status = struct.unpack_from("<H", report, 2)[0] if len(report) >= 4 else -1
        status_counts[str(status)] = status_counts.get(str(status), 0) + 1

    result = {"ticks_replayed": args.ticks, "strategy_entries": strategy.entries, "strategy_exits": strategy.exits, "strategy_stop_exits": strategy.stop_exits, "execution_reports": len(reports), "report_status_counts": status_counts, "elapsed_s": elapsed, "ticks_per_sec": args.ticks / elapsed, "engine_stderr": stderr}
    out = ROOT / "results" / "replay_e2e.json"; out.parent.mkdir(exist_ok=True); out.write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))

if __name__ == "__main__": main()