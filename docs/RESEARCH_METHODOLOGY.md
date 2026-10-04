# Sentinel StatArb Research Methodology

## Objective

Sentinel separates the statistical signal from the paper-execution model. The research result is intended to answer:

- Does the spread signal generate repeatable entries/exits under the chosen synthetic or replayed tick path?
- How does volatility-aware debouncing change turnover and flash-crash exposure?
- How sensitive is the result to execution costs, fill delay, thresholds, and rolling-window choices?

The output is scenario analysis, not a claim of live profitability.

## Signal construction

For every tick, the strategy marks both instruments at the midpoint:

m_A = (bid_A + ask_A) / 2
m_B = (bid_B + ask_B) / 2

A scalar Kalman filter updates the hedge ratio:

m_A = beta_t * m_B + epsilon_t

The spread is:

s_t = m_A - beta_t * m_B

The rolling mean and sample standard deviation over the configured window produce the z-score:

z_t = (s_t - mean(s)) / std(s)

A long-spread signal is generated when the z-score is sufficiently negative; a short-spread signal is generated when it is sufficiently positive.

## Volatility-aware protection

The dynamic debouncer increases the required number of consecutive confirmations as observed volatility rises. This is compared with a baseline mode using one confirmation.

An active position also owns an OCO stop-limit bracket. The stop and limit are expressed in spread units using the configured basis-point offsets. Once the stop triggers, the limit remains resting until the spread is again marketable at that level.

## Execution model

The portfolio simulator uses two real legs rather than a synthetic spread cash balance:

- Long spread: buy A and sell beta times B.
- Short spread: sell A and buy beta times B.
- Position size is normalized to a configurable target gross notional.
- Buys cross the ask and sells cross the bid.
- Configured slippage is then applied adversely to each leg.
- Commission is charged independently on each filled leg.
- Equity is marked at the two-leg midpoint.

Signals are not filled on the generating quote by default. execution_delay_ticks=1 schedules the target position for the next tick, avoiding same-tick signal/fill lookahead.

This remains a simplified paper model. It does not model queue position, partial fills, exchange matching rules, borrow, funding, financing, or market impact.

## Risk and cost outputs

Every run reports:

- total PnL and return percentage;
- maximum drawdown in currency and percentage;
- flash-crash equity loss over the configured crash window;
- commissions;
- bid/ask crossing cost;
- explicit slippage;
- combined cost;
- turnover;
- maximum gross and net exposure;
- trade count, mean-reversion exits, OCO stop-limit exits, win rate, average/best/worst trade;
- profit factor.

No Sharpe ratio or annualized metric is emitted by default because the synthetic tick horizon does not represent a defensible calendar sampling frequency.

## Robustness tests

The repository provides three complementary sweeps.

### Cost and crash sensitivity

scripts/sensitivity_backtest.py varies commission/slippage assumptions and crash locations.

### Seed and crash robustness

scripts/robustness_backtest.py runs multiple deterministic seeds and crash locations, then summarizes how often the dynamic protection improves PnL and how it changes drawdown/crash loss.

### Parameter sensitivity

scripts/parameter_sensitivity.py varies the entry z-score, exit z-score, and rolling window. The output is a ranking of scenario results, not a claim that the top configuration is optimal in the market.

## Persisted-data replay

scripts/replay_duckdb.py consumes the ticks table from DuckDB in batches and feeds the exact same run_ticks() research/execution engine used by synthetic tests. This keeps the model consistent between generated experiments and persisted telemetry.

## Evidence policy

A benchmark number is considered verified only when the corresponding command completes successfully and its output is preserved as a CI artifact or target-hardware result.

The documented latency values in the README are historical measurements from a specific GitHub Actions runner. New code changes require a fresh CI run before those values are treated as current.

Synthetic strategy improvements are not live-market performance claims.
