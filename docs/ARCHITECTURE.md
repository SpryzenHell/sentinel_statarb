# Sentinel StatArb architecture

## Runtime topology

```text
Cryptofeed L2 (optional live adapter)
        |
        v
Python normalization / PairStrategy
        |
        | TickMessage / OrderMessage
        v
   ZeroMQ PUSH/PULL
        |
        v
+-------------------------------+
| sentinel_exec                 |
|                               |
| ZMQ receive / output thread  |
|        |                      |
|        v                      |
|  lock-free SPSC input queue   |
|        |                      |
|        v                      |
| C++ execution thread          |
|  - quote-age validation       |
|  - simulated fills            |
|  - inventory / cash           |
|  - OCO state machine          |
|        |                      |
|        +--> SPSC report -----> ZMQ report PUSH
|        |                      |
|        +--> SPSC telemetry -> ZMQ PUB
+-------------------------------+
                                  |
                                  v
                         Python telemetry logger
                                  |
                           bounded work queue
                                  |
                                  v
                         asynchronous DuckDB
```

## Execution-thread ownership

The latency-sensitive thread owns the `ExecutionEngine` state. It does not call Python, DuckDB, or blocking ZeroMQ APIs. It communicates with the outer I/O thread through bounded SPSC queues.

The input queue is single-producer/single-consumer: the ZMQ receive side produces commands and the execution thread consumes them. The report and telemetry queues have the opposite ownership: the execution thread produces and the outer thread drains them.

## Quote freshness

`TickMessage.ts_ns` and the execution timestamp use a monotonic clock. An order is rejected when the latest quote age exceeds `max_quote_age_us`. This prevents a delayed strategy decision from being simulated against an obsolete book.

## OCO risk state

An entry arms a stop level and a separate limit level. A stop breach changes the bracket into a resting limit state. The position is only flattened when the limit condition is executable; a gap beyond the limit does not create a fictitious fill.

## Telemetry

Telemetry is intentionally separated from the execution hot path. The execution thread only copies a trivially-copyable message into an SPSC queue. ZeroMQ publication and DuckDB persistence happen outside the execution thread.

## Why Python remains useful

Python owns research iteration, statistical modeling, deterministic scenario generation, and the optional live-feed adapter. C++ owns the latency-sensitive execution and inventory state so Python scheduling and interpreter overhead are not in the simulated matching path.