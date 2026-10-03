#include "sentinel/execution_engine.hpp"

#include <chrono>
#include <cmath>

namespace sentinel {

ExecutionEngine::ExecutionEngine(EngineConfig cfg) : cfg_(cfg) {}

std::uint64_t ExecutionEngine::now_ns() noexcept {
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());
}

double ExecutionEngine::apply_slippage(double px, Side side, double bps) noexcept {
  return px * (1.0 + static_cast<int>(side) * bps * 1e-4);
}

double ExecutionEngine::spread() const noexcept {
  if (!have_quote_) return 0.0;
  const double mid_a = 0.5 * (last_tick_.bid_a + last_tick_.ask_a);
  const double mid_b = 0.5 * (last_tick_.bid_b + last_tick_.ask_b);
  return mid_a - cfg_.hedge_ratio * mid_b;
}

void ExecutionEngine::on_tick(const TickMessage& tick) {
  last_tick_ = tick;
  have_quote_ = true;
  ++state_.ticks;
}

bool ExecutionEngine::on_order(const OrderMessage& order, ReportMessage& report) {
  report = {};
  report.type = MessageType::kReport;
  report.id = order.id;
  report.recv_ts_ns = now_ns();
  report.side = order.side;
  report.qty = order.qty;

  ++state_.orders;
  if (!have_quote_) return false;

  const auto age_us = (report.recv_ts_ns > last_tick_.ts_ns)
      ? static_cast<double>(report.recv_ts_ns - last_tick_.ts_ns) / 1e3
      : 0.0;
  if (age_us > cfg_.max_quote_age_us) {
    report.status = 2;  // stale quote reject
    ++state_.stale_rejects;
    return false;
  }

  const double a = (order.side == Side::kBuy) ? last_tick_.ask_a : last_tick_.bid_a;
  const double b = (order.side == Side::kBuy) ? last_tick_.bid_b : last_tick_.ask_b;
  const Side hedge_side = (order.side == Side::kBuy) ? Side::kSell : Side::kBuy;

  report.status = 1;  // fill
  report.fill_a = apply_slippage(a, order.side, cfg_.slippage_bps);
  report.fill_b = apply_slippage(b, hedge_side, cfg_.slippage_bps);
  report.spread = report.fill_a - cfg_.hedge_ratio * report.fill_b;
  ++state_.fills;

  const double signed_qty = static_cast<int>(order.side) * order.qty;
  state_.position_a += signed_qty;
  state_.position_b -= cfg_.hedge_ratio * signed_qty;
  state_.cash -= signed_qty * report.fill_a;
  state_.cash += cfg_.hedge_ratio * signed_qty * report.fill_b;

  if (!oco_active_) {
    oco_active_ = true;
    open_side_ = order.side;
    entry_spread_ = report.spread;
    entry_notional_ = std::abs(0.5 * (last_tick_.bid_a + last_tick_.ask_a))
                    + std::abs(cfg_.hedge_ratio * 0.5 * (last_tick_.bid_b + last_tick_.ask_b));
    const double stop_offset = entry_notional_ * cfg_.oco_stop_bps * 1e-4;
    const double limit_offset = entry_notional_ * cfg_.oco_stop_bps * 1e-4;
    stop_spread_ = entry_spread_ - static_cast<int>(open_side_) * stop_offset;
    limit_spread_ = stop_spread_ - static_cast<int>(open_side_) * limit_offset;
  }

  report.oco_stop_spread = stop_spread_;
  report.oco_limit_spread = limit_spread_;

  const bool opposite = (open_side_ == Side::kBuy && order.side == Side::kSell) ||
                        (open_side_ == Side::kSell && order.side == Side::kBuy);
  if (oco_active_ && opposite && std::abs(state_.position_a) < 1e-12) {
    oco_active_ = false;
  }
  return true;
}

bool ExecutionEngine::check_oco(ReportMessage& report) {
  if (!oco_active_ || !have_quote_) return false;
  const double s = spread();
  const bool hit = (open_side_ == Side::kBuy) ? (s <= stop_spread_) : (s >= stop_spread_);
  if (!hit) return false;

  report = {};
  report.type = MessageType::kReport;
  report.id = 0;  // system-generated OCO exit
  report.recv_ts_ns = now_ns();
  report.side = (open_side_ == Side::kBuy) ? Side::kSell : Side::kBuy;
  report.qty = std::abs(state_.position_a);
  report.fill_a = (report.side == Side::kBuy) ? last_tick_.ask_a : last_tick_.bid_a;
  report.fill_b = (report.side == Side::kBuy) ? last_tick_.bid_b : last_tick_.ask_b;
  report.spread = s;
  report.oco_stop_spread = stop_spread_;
  report.oco_limit_spread = limit_spread_;
  report.status = 3;  // OCO stop execution

  state_.cash -= state_.position_a * report.fill_a;
  state_.cash += state_.position_b * report.fill_b;
  state_.position_a = 0.0;
  state_.position_b = 0.0;
  oco_active_ = false;
  ++state_.stop_events;
  ++state_.fills;
  return true;
}

} // namespace sentinel
