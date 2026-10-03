#include "sentinel/execution_engine.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <vector>

static std::uint64_t now_ns() {
  return static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count());
}

int main(int argc, char** argv) {
  const int n = argc > 1 ? std::stoi(argv[1]) : 200000;
  sentinel::ExecutionEngine engine({1.0, 1.0, 5.0, 250000.0});
  sentinel::TickMessage tick{};
  tick.type = sentinel::MessageType::kTick;
  tick.bid_a = 100.0; tick.ask_a = 100.01;
  tick.bid_b = 100.0; tick.ask_b = 100.01;
  tick.volatility = 0.001;
  std::vector<double> us; us.reserve(n);
  for (int i = 0; i < 1000; ++i) {
    tick.ts_ns = now_ns(); tick.seq = static_cast<std::uint64_t>(i); engine.on_tick(tick);
    sentinel::OrderMessage warm{}; warm.type=sentinel::MessageType::kOrder; warm.side=sentinel::Side::kBuy; warm.id=i; warm.ts_ns=tick.ts_ns; warm.qty=1.0;
    sentinel::ReportMessage r{}; engine.on_order(warm,r);
  }
  engine = sentinel::ExecutionEngine({1.0, 1.0, 5.0, 250000.0});
  for (int i = 0; i < n; ++i) {
    tick.ts_ns = now_ns(); tick.seq = static_cast<std::uint64_t>(i);
    engine.on_tick(tick);
    sentinel::OrderMessage order{}; order.type=sentinel::MessageType::kOrder; order.side=(i%2==0)?sentinel::Side::kBuy:sentinel::Side::kSell; order.id=i; order.ts_ns=tick.ts_ns; order.qty=1.0;
    sentinel::ReportMessage report{};
    const auto t0=std::chrono::steady_clock::now();
    engine.on_order(order,report);
    const auto t1=std::chrono::steady_clock::now();
    us.push_back(std::chrono::duration<double,std::micro>(t1-t0).count());
  }
  std::sort(us.begin(),us.end());
  auto pct=[&](double p){ return us[static_cast<std::size_t>(p*(us.size()-1))]; };
  std::cout<<std::fixed<<std::setprecision(3)
           <<"orders="<<n<<" median_us="<<pct(.50)<<" p99_us="<<pct(.99)<<" p99_9_us="<<pct(.999)
           <<" fills="<<engine.state().fills<<" stale_rejects="<<engine.state().stale_rejects<<"\n";
}