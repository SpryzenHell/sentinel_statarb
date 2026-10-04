#pragma once

#include <cstdint>

#include "sentinel/protocol.hpp"

namespace sentinel {

struct EngineConfig {
  double hedge_ratio{1.0};
  double slippage_bps{1.0};
  double oco_stop_bps{5.0};
  double oco_limit_bps{5.0};
  double max_quote_age_us{250.0};
  double commission_bps{0.0};
};

struct EngineState {
  std::uint64_t ticks{0};
  std::uint64_t orders{0};
  std::uint64_t fills{0};
  std::uint64_t stale_rejects{0};
  std::uint64_t invalid_ticks{0};
  std::uint64_t stop_events{0};
  double cash{0.0};
  double position_a{0.0};
  double position_b{0.0};
};

class ExecutionEngine {
 public:
  explicit ExecutionEngine(EngineConfig cfg = {});

  void on_tick(const TickMessage& tick);
  bool on_order(const OrderMessage& order, ReportMessage& report);
  bool check_oco(ReportMessage& report);

  const EngineState& state() const noexcept { return state_; }

 private:
  static std::uint64_t now_ns() noexcept;
  static double apply_slippage(double px, Side side, double bps) noexcept;
  double spread() const noexcept;

  EngineConfig cfg_;
  EngineState state_{};
  TickMessage last_tick_{};
  bool have_quote_{false};
  bool oco_active_{false};
  bool stop_triggered_{false};
  Side open_side_{Side::kBuy};
  double entry_spread_{0.0};
  double stop_spread_{0.0};
  double limit_spread_{0.0};
  double entry_notional_{100.0};
};

} // namespace sentinel
