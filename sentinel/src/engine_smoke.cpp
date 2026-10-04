#include "sentinel/execution_engine.hpp"

#include <chrono>
#include <cstdint>
#include <iostream>
#include <stdexcept>

static std::uint64_t now_ns() {
  return static_cast<std::uint64_t>(
      std::chrono::duration_cast<std::chrono::nanoseconds>(
          std::chrono::steady_clock::now().time_since_epoch()).count());
}

static void require(bool ok, const char* msg) {
  if (!ok) throw std::runtime_error(msg);
}

int main() {
  bool rejected_bad_config = false;
  try {
    sentinel::ExecutionEngine bad({0.0, 0.0, 5.0, 5.0, 250.0});
  } catch (const std::invalid_argument&) {
    rejected_bad_config = true;
  }
  require(rejected_bad_config, "invalid engine configuration was accepted");

  sentinel::ExecutionEngine engine({1.0, 0.0, 5.0, 5.0, 250.0});

  const auto ts = now_ns();
  sentinel::TickMessage tick{};
  tick.type = sentinel::MessageType::kTick;
  tick.ts_ns = ts;
  tick.bid_a = 100.0;
  tick.ask_a = 100.01;
  tick.bid_b = 100.0;
  tick.ask_b = 100.01;
  tick.volatility = 0.001;
  engine.on_tick(tick);

  sentinel::OrderMessage order{};
  order.type = sentinel::MessageType::kOrder;
  order.side = sentinel::Side::kBuy;
  order.id = 1;
  order.ts_ns = ts;
  order.qty = 1.0;

  sentinel::ReportMessage report{};
  require(engine.on_order(order, report), "fresh order was rejected");
  require(report.status == 1, "fresh order status wrong");
  require(report.oco_stop_spread < report.spread, "OCO stop was not armed");
  require(report.oco_limit_spread < report.oco_stop_spread, "OCO limit was not offset");
  require(engine.state().fills == 1, "fill counter wrong");

  tick.ts_ns = now_ns();
  tick.bid_a = 99.0;
  tick.ask_a = 99.01;
  engine.on_tick(tick);
  require(!engine.check_oco(report), "OCO should not fill below the limit");
  tick.bid_a = 99.75;
  tick.ask_a = 99.76;
  engine.on_tick(tick);
  require(engine.check_oco(report), "OCO limit did not fill after recovery");
  require(report.status == 3, "OCO status wrong");
  require(engine.state().position_a == 0.0, "position not flattened");
  require(engine.state().stop_events == 1, "stop counter wrong");

  tick.ts_ns = now_ns() - 1'000'000;
  engine.on_tick(tick);
  order.id = 2;
  order.ts_ns = tick.ts_ns;
  require(!engine.on_order(order, report), "stale order was accepted");
  require(engine.state().stale_rejects == 1, "stale counter wrong");

  tick.ts_ns = now_ns();
  engine.on_tick(tick);
  order.id = 3;
  order.side = static_cast<sentinel::Side>(0);
  order.qty = 1.0;
  order.ts_ns = tick.ts_ns;
  require(!engine.on_order(order, report), "invalid side was accepted");
  require(report.status == 4, "invalid order status wrong");

  std::cout << "engine_smoke=PASS\n";
}
