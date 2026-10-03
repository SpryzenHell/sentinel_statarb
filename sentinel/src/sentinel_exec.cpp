#include "sentinel/execution_engine.hpp"
#include "sentinel/protocol.hpp"
#include <rigtorp/SPSCQueue.h>
#include <zmq.h>

#include <atomic>
#include <cerrno>
#include <cstring>
#include <iostream>
#include <string>
#include <thread>

namespace {
struct Command {
  sentinel::MessageType type{sentinel::MessageType::kShutdown};
  sentinel::TickMessage tick{};
  sentinel::OrderMessage order{};
};
void print_stats(const sentinel::EngineState& s) {
  std::cerr << "ticks=" << s.ticks << " orders=" << s.orders
            << " fills=" << s.fills << " stale_rejects=" << s.stale_rejects
            << " stop_events=" << s.stop_events << "\n";
}
}
int main(int argc, char** argv) {
  const std::string endpoint = (argc > 1) ? argv[1] : "ipc:///tmp/sentinel_exec_in.ipc";
  void* ctx = zmq_ctx_new();
  void* pull = zmq_socket(ctx, ZMQ_PULL);
  void* push = zmq_socket(ctx, ZMQ_PUSH);
  if (!ctx || !pull || !push) return 2;
  if (zmq_bind(pull, endpoint.c_str()) != 0) { std::cerr << "bind failed: " << std::strerror(errno) << "\n"; return 3; }
  const std::string out = endpoint + ".reports";
  if (zmq_bind(push, out.c_str()) != 0) { std::cerr << "report bind failed: " << std::strerror(errno) << "\n"; return 4; }

  rigtorp::SPSCQueue<Command> input_queue(4096);
  rigtorp::SPSCQueue<sentinel::ReportMessage> output_queue(4096);
  std::atomic<bool> running{true};
  sentinel::ExecutionEngine engine;

  std::thread execution_thread([&] {
    while (running.load(std::memory_order_acquire) || !input_queue.empty()) {
      auto* command = input_queue.front();
      if (!command) { std::this_thread::yield(); continue; }
      if (command->type == sentinel::MessageType::kShutdown) {
        input_queue.pop();
        running.store(false, std::memory_order_release);
        break;
      }
      if (command->type == sentinel::MessageType::kTick) {
        engine.on_tick(command->tick);
        sentinel::ReportMessage report{};
        if (engine.check_oco(report)) { while (!output_queue.try_push(report)) std::this_thread::yield(); }
      } else if (command->type == sentinel::MessageType::kOrder) {
        sentinel::ReportMessage report{};
        engine.on_order(command->order, report);
        while (!output_queue.try_push(report)) std::this_thread::yield();
      }
      input_queue.pop();
    }
  });

  alignas(64) std::byte buf[256];
  while (running.load(std::memory_order_acquire)) {
    while (auto* report = output_queue.front()) { zmq_send(push, report, sizeof(*report), 0); output_queue.pop(); }
    zmq_pollitem_t item{pull, 0, ZMQ_POLLIN, 0};
    const int ready = zmq_poll(&item, 1, 1);
    if (ready <= 0) continue;
    const int n = zmq_recv(pull, buf, sizeof(buf), ZMQ_DONTWAIT);
    if (n < 1) continue;
    const auto type = static_cast<sentinel::MessageType>(static_cast<std::uint8_t>(buf[0]));
    Command command{}; command.type = type;
    if (type == sentinel::MessageType::kTick && n == static_cast<int>(sizeof(sentinel::TickMessage))) {
      std::memcpy(&command.tick, buf, sizeof(command.tick));
    } else if (type == sentinel::MessageType::kOrder && n == static_cast<int>(sizeof(sentinel::OrderMessage))) {
      std::memcpy(&command.order, buf, sizeof(command.order));
    } else if (type == sentinel::MessageType::kShutdown) {
      while (!input_queue.try_push(command)) std::this_thread::yield();
      break;
    } else { continue; }
    while (!input_queue.try_push(command)) std::this_thread::yield();
  }

  execution_thread.join();
  while (auto* report = output_queue.front()) { zmq_send(push, report, sizeof(*report), 0); output_queue.pop(); }
  print_stats(engine.state());
  zmq_close(push); zmq_close(pull); zmq_ctx_term(ctx);
  return 0;
}