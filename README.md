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
pip install -e '.[full]'
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
