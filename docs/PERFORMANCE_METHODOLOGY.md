# Sentinel StatArb performance methodology

## Measurement rules

All latency claims are benchmark outputs recorded from the repository. A number is not placed in the README as a fact until a benchmark has produced it.

Report three percentiles when possible: median, p99, and p99.9. Record CPU/OS state with `scripts/system_profile.py` so measurements are tied to a concrete host.

## Benchmark mapping

| Benchmark | Measures | Does not prove |
|---|---|---|
| `sentinel_engine_bench` | direct C++ `on_order` execution cost | network/IPC latency or a specific HPC cluster |
| `sentinel_spsc_bench` | throughput of the pinned Rigtorp SPSC implementation | end-to-end strategy throughput |
| `sentinel_zmq_bench` | synchronous local ZeroMQ request/response path | one-way transport latency |
| `sentinel_zmq_oneway` | one-way `ipc://` delivery using monotonic timestamps across forked processes | cross-machine/network latency |
| `benchmark_ipc.py` | Python-to-C++ report round trip | raw C++ engine cost |
| `run_replay.py` | Python strategy → ZeroMQ → C++ execution integration | live-market performance |
| `benchmark_duckdb.py` | asynchronous batched DuckDB storage throughput | ZeroMQ delivery integrity |
| `benchmark_telemetry.py` | connected C++ telemetry → ZeroMQ → Python logger → DuckDB path | live exchange reliability |

## HPC procedure

1. Capture `python scripts/system_profile.py`.
2. Pin the execution thread with `--cpu N`.
3. Optionally request `--mlock` and `--fifo P` on a host where the OS policy permits them.
4. Run the direct engine, SPSC, one-way IPC, and connected telemetry benchmarks.
5. Store the resulting artifacts together with the host profile.

## Interpretation

A sub-millisecond direct C++ result is a property of the tested build and CPU. A sub-10-microsecond IPC result is only defensible for the exact transport mode and host that produced it. A 10M-row DuckDB result proves that the logger/storage path sustained that workload; it does not by itself prove that a live exchange feed can deliver ten million lossless messages under the same conditions.