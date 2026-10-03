import argparse
import json
import os
import struct
import subprocess
import sys
import time
from pathlib import Path

import zmq

ROOT = Path(__file__).parents[1]
TICK_FMT = '<BQQddddd'

def pack_tick(seq: int, ts_ns: int) -> bytes:
    return struct.pack(TICK_FMT, 1, seq, ts_ns, 100.0, 100.01, 100.0, 100.01, 0.001)

def main() -> None:
    ap = argparse.ArgumentParser(description='Benchmark connected Sentinel telemetry -> DuckDB path')
    ap.add_argument('--ticks', type=int, default=100_000)
    ap.add_argument('--batch', type=int, default=100_000)
    ap.add_argument('--db', default='results/telemetry.duckdb')
    args = ap.parse_args()

    exe = ROOT / 'build' / 'sentinel' / 'sentinel_exec'
    if not exe.exists():
        raise SystemExit('Build sentinel_exec first (requires libzmq3-dev).')

    endpoint = f'ipc:///tmp/sentinel_telemetry_{os.getpid()}'
    telemetry_endpoint = endpoint + '.telemetry'
    env = os.environ.copy(); env['PYTHONUNBUFFERED'] = '1'
    logger = subprocess.Popen(
        [sys.executable, str(ROOT / 'scripts' / 'telemetry_logger.py'),
         '--endpoint', telemetry_endpoint, '--expected-ticks', str(args.ticks),
         '--batch', str(args.batch), '--db', args.db],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env,
    )
    proc = subprocess.Popen([str(exe), endpoint], stderr=subprocess.PIPE, text=True)

    ready = logger.stdout.readline().strip() if logger.stdout else ''
    if ready != 'READY':
        raise SystemExit(f'Logger failed to initialize: {ready}')

    ctx = zmq.Context()
    push = ctx.socket(zmq.PUSH)
    push.connect(endpoint)
    time.sleep(0.15)

    started = time.perf_counter()
    for i in range(args.ticks):
        push.send(pack_tick(i, time.monotonic_ns()))
    push.send(b'\x03')
    push.close()
    ctx.term()

    proc.wait(timeout=30)
    logger.wait(timeout=30)
    elapsed = time.perf_counter() - started
    engine_stderr = proc.stderr.read().strip() if proc.stderr else ''
    logger_out = logger.stdout.read().strip() if logger.stdout else ''
    logger_err = logger.stderr.read().strip() if logger.stderr else ''

    result = {
        'ticks_sent': args.ticks,
        'elapsed_s': elapsed,
        'ticks_per_sec': args.ticks / elapsed if elapsed else 0.0,
        'engine_stats': engine_stderr,
        'logger_stdout': logger_out,
        'logger_stderr': logger_err,
        'connected_telemetry': True,
    }
    out = ROOT / 'results' / 'telemetry_e2e.json'; out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()