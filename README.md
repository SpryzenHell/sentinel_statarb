# Sentinel StatArb

Sentinel StatArb is a reproducible statistical-arbitrage research + simulated execution stack built around four layers:

1. **Market-data path:** the upstream Cryptofeed-derived material remains in the repository, while the active Sentinel pipeline consumes normalized L2-like ticks.
2. **Research path:** a Kalman hedge-ratio estimator, spread z-score, volatility-aware dynamic debouncer, and OCO stop-limit bracket implement the strategy/risk layer.
3. **Execution path:** a C++20 simulated execution engine separates the latency-sensitive execution loop from Python research code, uses a cache-line-aware SPSC ring, and exposes a ZeroMQ IPC boundary.
4. **Telemetry path:** an asynchronous Python writer batches ticks into DuckDB for replay and analytics; the full benchmark is designed for 10M+ rows.

## Resume-bullet mapping

### 1. Sub-millisecond C++ execution engine
`sentinel/src/execution_engine.cpp` contains quote validation, execution, inventory and OCO state. The engine is independent of Python and can be driven through `sentinel_exec` over ZeroMQ.

### 2. Flash-crash protection
`python/sentinel_statarb/strategy.py` contains `DynamicDebouncer` and `OCOBracket`. High-volatility signals require more consecutive confirmations, and the bracket uses an explicit 5 bps stop offset plus a separate limit offset. `scripts/run_backtest.py` compares baseline and protected behavior on a deterministic synthetic flash-crash path.

### 3. Stale-quote protection + low-latency IPC + DuckDB
The C++ engine rejects orders whose latest quote exceeds `max_quote_age_us`. `sentinel_zmq_bench` measures local ZeroMQ IPC latency, while `scripts/benchmark_duckdb.py` writes 10M ticks asynchronously in batches.

## Quick start

### Python research/backtest

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[full]'  # use '.[full,live]' for the optional Cryptofeed live bridge
python scripts/run_backtest.py
```

### C++ core

```bash
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
ctest --test-dir build --output-on-failure
./build/sentinel/sentinel_spsc_bench
```

### ZeroMQ execution process

On Linux with the libzmq development package installed:

```bash
sudo apt-get install libzmq3-dev
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build --parallel
python scripts/benchmark_ipc.py --orders 10000
```

### 10M+ DuckDB logging benchmark

```bash
python scripts/benchmark_duckdb.py --ticks 10000000 --batch 100000
```

The 10M-row run is intentionally separate from the default smoke tests because it is a heavier storage benchmark.


## Linux/HPC runtime profile

The execution process accepts optional runtime controls:

```bash
./build/sentinel/sentinel_exec ipc:///tmp/sentinel_exec_in.ipc --cpu 4
./build/sentinel/sentinel_exec ipc:///tmp/sentinel_exec_in.ipc --cpu 4 --mlock
./build/sentinel/sentinel_exec ipc:///tmp/sentinel_exec_in.ipc --cpu 4 --fifo 20
```

`--cpu` pins the execution thread to one logical CPU. `--mlock` requests `mlockall`; `--fifo` requests `SCHED_FIFO`. The process reports whether each request succeeded. These controls can require elevated privileges or scheduler limits on the host.

Capture host state before benchmarking:

```bash
python scripts/system_profile.py > results/system_profile.json
```

Direct C++ engine measurement with CPU pinning:

```bash
./build/sentinel/sentinel_engine_bench 200000 --cpu 4
```

Connected telemetry benchmark:

```bash
python scripts/benchmark_telemetry.py --ticks 10000000 --batch 100000 --cpu 4
```

The last command measures the C++ telemetry queue → ZeroMQ PUB/SUB → asynchronous DuckDB path. Use the host profile and benchmark artifact when discussing latency claims.

## Latest verified run

Verified in GitHub Actions on **2026-10-03**, run #41, Ubuntu x86_64, C++20/GCC 13.3, Python 3.12, with libzmq3-dev and DuckDB 1.5.6.

| Measurement | Result |
|---|---:|
| Python unit tests | 2/2 passed |
| C++ CTest suite | 3/3 passed |
| Direct C++ execution core | **0.070 us median / 0.080 us p99 / 0.130 us p99.9** |
| Rigtorp SPSC benchmark | **164.372 Mops/s**, 5M items |
| Python -> ZeroMQ -> C++ E2E | **768.774 orders/s**, 1,000 orders |
| Python strategy -> C++ execution replay | **5,000 ticks**, 5 entries, 5 exits, 10 execution reports |
| Replay throughput | **8,592.639 ticks/s** |
| ZeroMQ IPC transport | **39.082 us median / 47.499 us p99 / 59.230 us p99.9** |
| Async DuckDB logging | **10,000,000 rows**, **2,662,236 rows/s** |

The direct C++ core measurement supports a sub-millisecond **core-function benchmark** on this runner. It does not establish the original resume's separate “HPC” environment claim.

The ZeroMQ measurement is **not** sub-10 us on this runner, so that number should not be stated as a verified resume result without a dedicated target-hardware benchmark.

The strategy comparison is deterministic synthetic data. In this run, the dynamic debouncer reduced entries from 1,994 to 56 and reduced the absolute synthetic maximum drawdown from 6.786 to 0.194 spread units. That is a benchmark result for this synthetic scenario, not a claim about live trading performance.

## Reproducibility

All research benchmarks use fixed seeds and write machine-readable JSON results under `results/`. Latency/throughput numbers belong in this README only after the corresponding benchmark has actually been run on the target hardware.

## Upstream provenance

The intended source composition was supplied in `INPUT_projects.json`: Cryptofeed, Financial-Models-Numerical-Methods and Rigtorp SPSCQueue. Their upstream roles are preserved as provenance; the active Sentinel layer is project-specific integration code.

Upstream projects:

- https://github.com/bmoscon/cryptofeed
- https://github.com/cantaro86/Financial-Models-Numerical-Methods
- https://github.com/rigtorp/SPSCQueue

The existing `sentCryptofeed/`, `sentSrc/`, and `sentTests/` trees are retained for provenance but are not imported by the active package because the previous automated merge altered source syntax.

## Truthful benchmark policy

This repository does not claim “HPC”, “10M+ DuckDB”, “sub-10us”, or “sub-millisecond” as measured facts merely because the implementation supports those targets. The corresponding command and result file are the evidence record.

## Development window

The supplied project configuration lists the intended project window as **2026-02-01 through 2026-05-31**. That configuration is retained as input metadata; new commits use their real commit timestamps.
