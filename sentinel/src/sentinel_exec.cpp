#include "sentinel/execution_engine.hpp"
#include "sentinel/protocol.hpp"

#include <zmq.h>

#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>

namespace {
void print_stats(const sentinel::EngineState& s) {
  std::cerr << "ticks=" << s.ticks << " orders=" << s.orders
            << " fills=" << s.fills << " stale_rejects=" << s.stale_rejects
            << " stop_events=" << s.stop_events << '\n';
}
}

int main(int argc, char** argv) {
  const std::string endpoint =
      (argc > 1) ? argv[1] : "ipc:///tmp/sentinel_exec_in.ipc";
  void* ctx = zmq_ctx_new();
  void* pull = zmq_socket(ctx, ZMQ_PULL);
  void* push = zmq_socket(ctx, ZMQ_PUSH);
  if (!ctx || !pull || !push) return 2;
  if (zmq_bind(pull, endpoint.c_str()) != 0) {
    std::cerr << "bind failed: " << std::strerror(errno) << '\n';
    return 3;
  }
  const std::string out = endpoint + ".reports";
  if (zmq_bind(push, out.c_str()) != 0) {
    std::cerr << "report bind failed: " << std::strerror(errno) << '\n';
    return 4;
  }

  sentinel::ExecutionEngine engine;
  alignas(64) std::byte buf[256];

  while (true) {
    const int n = zmq_recv(pull, buf, sizeof(buf), 0);
    if (n < 1) continue;

    const auto type =
        static_cast<sentinel::MessageType>(static_cast<std::uint8_t>(buf[0]));

    if (type == sentinel::MessageType::kTick &&
        n == static_cast<int>(sizeof(sentinel::TickMessage))) {
      sentinel::TickMessage msg{};
      std::memcpy(&msg, buf, sizeof(msg));
      engine.on_tick(msg);

      sentinel::ReportMessage report{};
      if (engine.check_oco(report)) {
        zmq_send(push, &report, sizeof(report), 0);
      }
    } else if (type == sentinel::MessageType::kOrder &&
               n == static_cast<int>(sizeof(sentinel::OrderMessage))) {
      sentinel::OrderMessage msg{};
      std::memcpy(&msg, buf, sizeof(msg));

      sentinel::ReportMessage report{};
      engine.on_order(msg, report);
      zmq_send(push, &report, sizeof(report), 0);
    } else if (type == sentinel::MessageType::kShutdown) {
      break;
    }
  }

  print_stats(engine.state());
  zmq_close(push);
  zmq_close(pull);
  zmq_ctx_term(ctx);
  return 0;
}
