import argparse
import json
import os
import queue
import struct
import threading
import time
from pathlib import Path

import zmq

TICK_FMT = '<BQQddddd'
REPORT_FMT = '<BbHQQdddddd'
TICK_SIZE = struct.calcsize(TICK_FMT)
REPORT_SIZE = struct.calcsize(REPORT_FMT)

def main() -> None:
    ap = argparse.ArgumentParser(description='Asynchronous Sentinel telemetry logger')
    ap.add_argument('--endpoint', required=True)
    ap.add_argument('--expected-ticks', type=int, default=0)
    ap.add_argument('--db', default='results/telemetry.duckdb')
    ap.add_argument('--batch', type=int, default=100000)
    ap.add_argument('--ready-file', default='')
    args = ap.parse_args()

    import duckdb
    root = Path(__file__).parents[1]
    db = root / args.db
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists(): db.unlink()

    con = duckdb.connect(str(db))
    con.execute('CREATE TABLE ticks(seq BIGINT, ts_ns BIGINT, bid_a DOUBLE, ask_a DOUBLE, bid_b DOUBLE, ask_b DOUBLE, volatility DOUBLE)')
    con.execute('CREATE TABLE reports(id BIGINT, status INTEGER, ts_ns BIGINT, fill_a DOUBLE, fill_b DOUBLE, qty DOUBLE, spread DOUBLE, oco_stop_spread DOUBLE, oco_limit_spread DOUBLE)')

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.SUB)
    sock.setsockopt(zmq.RCVHWM, 1000000)
    sock.setsockopt(zmq.SUBSCRIBE, b'')
    sock.connect(args.endpoint)

    work: queue.Queue[object] = queue.Queue(maxsize=8)
    stop = object()
    started = time.perf_counter()
    ticks_received = 0
    reports_received = 0
    ticks_written = 0
    reports_written = 0
    lock = threading.Lock()

    def writer() -> None:
        nonlocal ticks_written, reports_written
        tick_batch = []
        report_batch = []
        while True:
            item = work.get()
            if item is stop:
                work.task_done()
                if tick_batch:
                    con.executemany('INSERT INTO ticks VALUES (?, ?, ?, ?, ?, ?, ?)', tick_batch)
                    ticks_written += len(tick_batch)
                if report_batch:
                    con.executemany('INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', report_batch)
                    reports_written += len(report_batch)
                return
            kind, payload = item
            if kind == 'tick':
                tick_batch.append(payload)
            else:
                report_batch.append(payload)
            if len(tick_batch) >= args.batch:
                con.executemany('INSERT INTO ticks VALUES (?, ?, ?, ?, ?, ?, ?)', tick_batch)
                with lock: ticks_written += len(tick_batch)
                tick_batch.clear()
            if len(report_batch) >= args.batch:
                con.executemany('INSERT INTO reports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', report_batch)
                with lock: reports_written += len(report_batch)
                report_batch.clear()
            work.task_done()

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    if args.ready_file:
        Path(args.ready_file).write_text('READY\n', encoding='utf-8')
    print('READY', flush=True)

    while True:
        message = sock.recv()
        if len(message) == TICK_SIZE:
            _, seq, ts_ns, bid_a, ask_a, bid_b, ask_b, volatility = struct.unpack(TICK_FMT, message)
            work.put(('tick', (seq, ts_ns, bid_a, ask_a, bid_b, ask_b, volatility)))
            ticks_received += 1
        elif len(message) == REPORT_SIZE:
            _, side, status, oid, ts_ns, fill_a, fill_b, qty, spread, stop_spread, limit_spread = struct.unpack(REPORT_FMT, message)
            work.put(('report', (oid, status, ts_ns, fill_a, fill_b, qty, spread, stop_spread, limit_spread)))
            reports_received += 1
        else:
            continue

        if args.expected_ticks and ticks_received >= args.expected_ticks:
            break

    work.put(stop)
    work.join()
    thread.join()
    with lock:
        final_ticks = ticks_written
        final_reports = reports_written
    elapsed = time.perf_counter() - started
    con.close()
    sock.close(0)
    ctx.term()

    result = {
        'expected_ticks': args.expected_ticks,
        'rows_written': final_ticks,
        'reports_written': final_reports,
        'elapsed_s': elapsed,
        'rows_per_sec': final_ticks / elapsed if elapsed else 0.0,
        'async_writer': True,
        'transport': 'ZeroMQ telemetry PUB/SUB',
        'backend': 'duckdb',
    }
    path = root / 'results' / 'telemetry_logger.json'
    path.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print('DONE', json.dumps(result), flush=True)

if __name__ == '__main__':
    main()